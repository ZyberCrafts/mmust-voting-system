# runserver.py
import subprocess
import sys
import os
import time
import signal
import threading
import webbrowser
import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)

# Configuration
USE_DAPHNE = True  # Set to False to force Django runserver
DAPHNE_PORT = 8000
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379

def is_redis_running():
    try:
        subprocess.run(['redis-cli', '-h', REDIS_HOST, '-p', str(REDIS_PORT), 'ping'],
                       capture_output=True, check=True, timeout=2)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

def start_redis():
    if is_redis_running():
        print(f"{Fore.GREEN}Redis is already running on {REDIS_HOST}:{REDIS_PORT}")
        return None
    print(f"{Fore.YELLOW}Starting Redis server...")
    try:
        proc = subprocess.Popen(['redis-server'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0)
        time.sleep(2)
        if is_redis_running():
            print(f"{Fore.GREEN}Redis started.")
            return proc
        else:
            print(f"{Fore.RED}Failed to start Redis. Please start it manually.")
            return None
    except FileNotFoundError:
        print(f"{Fore.RED}Redis executable not found. Install Redis and add to PATH.")
        return None

def run_service(cmd, name, color, show_output=True):
    """Run a command, print its output with color prefix in a separate thread."""
    try:
        if sys.platform == 'win32':
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, bufsize=1)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, bufsize=1)
    except Exception as e:
        print(f"{Fore.RED}Failed to start {name}: {e}")
        return None

    def output_reader():
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(f"{color}[{name}]{Style.RESET_ALL} {line.rstrip()}")
        proc.stdout.close()

    thread = threading.Thread(target=output_reader, daemon=True)
    thread.start()
    return proc

def main():
    processes = []
    
    # Start Redis
    redis_proc = start_redis()
    if redis_proc:
        processes.append(redis_proc)

    # Check if Daphne is available
    daphne_available = False
    try:
        subprocess.run([sys.executable, '-m', 'daphne', '--version'], capture_output=True, check=True)
        daphne_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Choose server
    if USE_DAPHNE and daphne_available:
        server_cmd = [sys.executable, '-m', 'daphne', '-b', '0.0.0.0', '-p', str(DAPHNE_PORT), 'mmust_voting.asgi:application']
        server_name = "Daphne (ASGI with WebSocket)"
        server_color = Fore.GREEN
        print(f"{Fore.GREEN}Using Daphne (WebSocket support enabled)")
    else:
        if USE_DAPHNE and not daphne_available:
            print(f"{Fore.YELLOW}Daphne not installed. Falling back to Django runserver (WebSocket will NOT work).")
            print(f"{Fore.YELLOW}To enable WebSocket, run: pip install daphne")
        server_cmd = [sys.executable, 'manage.py', 'runserver', f'0.0.0.0:{DAPHNE_PORT}']
        server_name = "Django runserver (no WebSocket)"
        server_color = Fore.GREEN

    # Celery worker (Windows: use -P solo)
    if sys.platform == 'win32':
        worker_cmd = ['celery', '-A', 'mmust_voting', 'worker', '-l', 'info', '-P', 'solo']
    else:
        worker_cmd = ['celery', '-A', 'mmust_voting', 'worker', '-l', 'info']

    # Celery beat with built‑in persistent scheduler (no extra package)
    beat_cmd = ['celery', '-A', 'mmust_voting', 'beat', '-l', 'info', '--scheduler', 'celery.beat.PersistentScheduler']

    # Start services
    server_proc = run_service(server_cmd, server_name, server_color)
    worker_proc = run_service(worker_cmd, "Celery worker", Fore.CYAN)
    beat_proc = run_service(beat_cmd, "Celery beat", Fore.MAGENTA)

    processes = [p for p in [server_proc, worker_proc, beat_proc] if p]

    # Print the local URL for easy access
    url = f"http://localhost:{DAPHNE_PORT}"
    print(f"\n{Fore.GREEN}All services started.")
    print(f"{Fore.CYAN}Open your browser at: {Fore.BLUE}{url}{Fore.CYAN} (Ctrl+click to follow)")
    print(f"{Fore.YELLOW}Press Ctrl+C to stop all services.\n")

    # Optionally open the URL automatically (uncomment next line)
    # webbrowser.open(url)

    def signal_handler(sig, frame):
        print(f"\n{Fore.YELLOW}Shutting down services...")
        for proc in processes:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print(f"{Fore.GREEN}All services stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Keep main thread alive
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == '__main__':
    main()