"""Environment report for deciding where to transcribe (local GPU / local CPU / cloud) and whether setup is complete.
usage: python scripts/doctor.py   (no job file needed)"""
import os, sys, platform, shutil, subprocess, importlib

def ok(flag):
    return 'ok ' if flag else 'MISSING'

def main():
    print(f'python      {sys.version.split()[0]}  ({sys.executable})')
    if 'anaconda' in sys.executable.lower() or 'conda' in sys.prefix.lower():
        print('  !! this looks like an Anaconda/conda Python: its old msvcp140.dll crashes CTranslate2 on Windows -> use the uv env from setup')
    print(f'platform    {platform.platform()}  cpu threads: {os.cpu_count()}')
    try:
        if os.name == 'nt':
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong)] + \
                           [(n, ctypes.c_ulonglong) for n in ('a', 'b', 'c', 'd', 'e', 'f')]
            m = MS(); m.dwLength = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            ram = m.ullTotalPhys
        else:
            ram = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        print(f'ram         {ram / 2**30:.1f} GB')
    except Exception:
        pass
    smi = shutil.which('nvidia-smi')
    if smi:
        r = subprocess.run([smi, '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'], capture_output=True, text=True)
        print('nvidia gpu  ' + (r.stdout.strip() or r.stderr.strip()))
    else:
        print('nvidia gpu  none found (nvidia-smi not on PATH)')
    for mod in ('faster_whisper', 'ctranslate2', 'av', 'cv2', 'numpy', 'PIL', 'pypdf', 'pypdfium2', 'reportlab'):
        try:
            m = importlib.import_module(mod)
            print(f'{mod:15s}{ok(True)} {getattr(m, "__version__", "")}')
        except Exception as e:
            print(f'{mod:15s}{ok(False)} ({type(e).__name__})')
    try:
        import ctranslate2
        print(f'cuda devs   {ctranslate2.get_cuda_device_count()} (CTranslate2)')
    except Exception:
        pass
    fonts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')
    for f in ('NanumPenScript-Regular.ttf', 'NotoSansKR[wght].ttf'):
        print(f'font        {ok(os.path.exists(os.path.join(fonts, f)))} {f}' + ('' if os.path.exists(os.path.join(fonts, f)) else '  -> python scripts/fetch_fonts.py'))
    print('next: python scripts/transcribe.py --probe-only  (from the course folder with lecnotes_job.json) measures transcription speed')

if __name__ == '__main__':
    main()
