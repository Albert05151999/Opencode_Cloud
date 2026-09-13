import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def fake_command(directory,name,body):
    path=directory/name;path.write_text('#!/bin/sh\n'+body+'\n');path.chmod(0o755)


def test_missing_host_prerequisites_fail_before_system_mutation(tmp_path):
    script=tmp_path/'install-docker.sh';shutil.copy2(ROOT/'build_image/docker/install-docker.sh',script)
    binary=tmp_path/'bin';binary.mkdir()
    fake_command(binary,'dirname',f'echo "{tmp_path}"')
    fake_command(binary,'uname','if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi')
    fake_command(binary,'id','echo 0')
    fake_command(binary,'install',f'echo mutation > "{tmp_path}/must-not-exist"')
    result=subprocess.run(['/bin/sh',str(script)],env={'PATH':str(binary)},capture_output=True,text=True)
    assert result.returncode!=0 and 'Missing host prerequisites:' in result.stderr
    assert 'iptables' in result.stderr and 'systemctl' in result.stderr and 'never downloads' in result.stderr
    assert not (tmp_path/'must-not-exist').exists()


def test_existing_engine_and_compose_are_reused(tmp_path):
    script=tmp_path/'install-docker.sh';shutil.copy2(ROOT/'build_image/docker/install-docker.sh',script)
    binary=tmp_path/'bin';binary.mkdir()
    fake_command(binary,'dirname',f'echo "{tmp_path}"')
    fake_command(binary,'uname','if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi')
    fake_command(binary,'timeout','shift; exec "$@"')
    fake_command(binary,'docker','[ "$1 $2" = "compose version" ] || [ "$1" = info ]')
    result=subprocess.run(['/bin/sh',str(script)],env={'PATH':str(binary)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_existing_daemon_waits_until_socket_ready(tmp_path):
    script=tmp_path/'install-docker.sh';shutil.copy2(ROOT/'build_image/docker/install-docker.sh',script)
    binary=tmp_path/'bin';binary.mkdir()
    fake_command(binary,'dirname',f'echo "{tmp_path}"')
    fake_command(binary,'uname','if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi')
    count=tmp_path/'count'
    fake_command(binary,'timeout','shift; exec "$@"')
    fake_command(binary,'docker',f'if [ "$1 $2" = "compose version" ]; then exit 0; fi; COUNT=0; if [ -f "{count}" ]; then read COUNT < "{count}"; fi; COUNT=$((COUNT + 1)); echo "$COUNT" > "{count}"; [ "$COUNT" -ge 3 ]')
    fake_command(binary,'sleep',':')
    result=subprocess.run(['/bin/sh',str(script)],env={'PATH':str(binary)},capture_output=True,text=True)
    assert result.returncode==0 and count.read_text().strip()=='3'


def test_existing_daemon_timeout_is_bounded_and_does_not_dump_logs(tmp_path):
    script=tmp_path/'install-docker.sh';shutil.copy2(ROOT/'build_image/docker/install-docker.sh',script)
    binary=tmp_path/'bin';binary.mkdir()
    fake_command(binary,'dirname',f'echo "{tmp_path}"')
    fake_command(binary,'uname','if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi')
    fake_command(binary,'timeout','shift; exec "$@"')
    fake_command(binary,'docker','if [ "$1 $2" = "compose version" ]; then exit 0; fi; echo private-diagnostic >&2; exit 1')
    fake_command(binary,'sleep',':')
    result=subprocess.run(['/bin/sh',str(script)],env={'PATH':str(binary)},capture_output=True,text=True,timeout=5)
    assert result.returncode!=0 and '60 seconds' in result.stderr and 'journalctl -u docker' in result.stderr
    assert 'private-diagnostic' not in result.stderr
