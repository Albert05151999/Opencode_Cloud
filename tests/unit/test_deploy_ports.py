import importlib.util
import os
from pathlib import Path
import socket

import pytest


@pytest.mark.skipif(os.name != 'posix', reason='Linux deployment socket semantics')
def test_port_probe_rejects_listener_but_accepts_closed_http_connection():
    spec=importlib.util.spec_from_file_location('deploy_doctor',Path(__file__).resolve().parents[2]/'deploy/doctor.py')
    doctor=importlib.util.module_from_spec(spec);spec.loader.exec_module(doctor)
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        assert not doctor.ports_idle([port])
        with socket.create_connection(('127.0.0.1',port)) as client:
            accepted,_=listener.accept()
            accepted.shutdown(socket.SHUT_WR)
            assert client.recv(1)==b''
            accepted.close()
    assert doctor.ports_idle([port])
