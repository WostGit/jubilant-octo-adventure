#!/usr/bin/env python3
"""Run an unprivileged Docker image and report cgroup v2 peak memory.

Requires Linux, Docker CLI, and sudo/root access to /sys/fs/cgroup.
"""
import argparse
import json
import pathlib
import subprocess
import time
import uuid


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def read_int(path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--memory', default='2g')
    args = parser.parse_args()
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    name = 'eg-' + uuid.uuid4().hex[:12]
    result = {'task': args.task, 'image': args.image, 'memory_limit': args.memory,
              'peak_bytes': None, 'peak_mib': None, 'exit_code': None,
              'oom_killed': False, 'timed_out': False, 'cgroup_peak_available': False}
    created = False
    try:
        # No privileged mode, host mounts, or Docker socket exposure to the task.
        docker('create', '--name', name, '--memory', args.memory,
               '--network', 'none', '--security-opt', 'no-new-privileges',
               '--cap-drop', 'ALL', args.image)
        created = True
        start = time.monotonic()
        docker('start', name)
        inspect = json.loads(docker('inspect', name).stdout)[0]
        pid = inspect['State']['Pid']
        cgroup_file = pathlib.Path(f'/proc/{pid}/cgroup')
        cg_path = None
        if cgroup_file.exists():
            for line in cgroup_file.read_text().splitlines():
                if line.startswith('0::'):
                    cg_path = pathlib.Path('/sys/fs/cgroup') / line.split('::', 1)[1].lstrip('/')
                    break
        # Docker's process may exit before /proc is sampled. Record absence explicitly.
        peak_path = cg_path / 'memory.peak' if cg_path else None
        result['cgroup_peak_available'] = bool(peak_path and peak_path.exists())
        while True:
            state = json.loads(docker('inspect', '--format', '{{json .State}}', name).stdout)
            if peak_path:
                peak = read_int(peak_path)
                if peak is not None:
                    result['peak_bytes'] = max(result['peak_bytes'] or 0, peak)
            if not state['Running']:
                result['exit_code'] = state['ExitCode']
                result['oom_killed'] = bool(state.get('OOMKilled', False))
                break
            if time.monotonic() - start > args.timeout:
                result['timed_out'] = True
                docker('kill', name, check=False)
                break
            time.sleep(0.25)
        result['duration_seconds'] = round(time.monotonic() - start, 2)
        if result['peak_bytes'] is not None:
            result['peak_mib'] = round(result['peak_bytes'] / 1048576, 2)
        result['logs_tail'] = docker('logs', '--tail', '80', name, check=False).stdout[-8000:]
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if created:
            docker('rm', '-f', name, check=False)
        output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    if result.get('error') or result['timed_out'] or result['oom_killed'] or result['exit_code'] != 0:
        raise SystemExit(1)
    if result['peak_bytes'] is None:
        print('WARNING: cgroup peak unavailable; do not interpret memory as zero.')


if __name__ == '__main__':
    main()
