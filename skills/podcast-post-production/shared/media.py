"""FFprobe transport only. Callers retain their own fields and acceptance rules."""
import json
import subprocess


def probe_json(path, *, entries=None, ffprobe='ffprobe', full=False, selector=None):
    command = [str(ffprobe), '-v', 'error']
    if selector:
        command += ['-select_streams', selector]
    if full:
        command += ['-show_streams', '-show_format']
    elif entries:
        command += ['-show_entries', entries]
    else:
        command += ['-show_format', '-show_streams']
    command += ['-of', 'json', str(path)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def duration_seconds(path, ffprobe='ffprobe'):
    payload = probe_json(path, entries='format=duration', ffprobe=ffprobe)
    return float(payload['format']['duration'])
