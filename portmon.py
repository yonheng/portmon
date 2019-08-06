import json
import logging
import os
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

home = str(Path(os.path.join(str(Path.home()), '.portmon')))
logging.basicConfig(level=logging.INFO, filename=str(Path(os.path.join(home, 'portmon.log'))))
_FINISH = False


def assert_exit(cond, msg):
    try:
        assert cond
    except AssertionError:
        logging.error('AssertionError of ' + msg)
        global _FINISH
        _FINISH = True


# TODO read ports from conf file
ports = ['9999', '9998', '9997', '9996', '9995']
usage_disk = {}
usage_last = {}

data_file = Path(os.path.join(home, 'data'))
data_path = str(data_file)
if not data_file.is_file():
    logging.error('debug no data file')
    with open(data_path, 'w') as fd:
        for p in ports:
            usage_disk[p] = 0
        fd.write(json.dumps(usage_disk))
else:
    logging.error('debug has data file')
    with open(data_path) as fd:
        usage_disk = json.load(fd)


def get_iptable():
    output = subprocess.check_output(['iptables', '-L', '-v', '-n', '-x'])
    return output.decode("utf-8").splitlines()


def add_ports_to_mon(unmoned_ports):
    for p in unmoned_ports:
        assert_exit(isinstance(p, str), 'add_ports_to_mon')
        out = subprocess.check_output(['iptables', '-A', 'OUTPUT', '-p', 'tcp', '--sport', str(p)])
        if out:
            logging.error("add_ports_to_mon fail")


def job():
    while True:
        if _FINISH:
            break
        table = get_iptable()

        first = 0
        for i, line in enumerate(table):
            if line.startswith("Chain OUTPUT"):
                first = i + 2

        ofs = 0
        full_outputs_list = []
        while table[first + ofs].strip():
            full_outputs_list.append(table[first + ofs])
            ofs += 1

        moned_list = []
        moned_ports = []
        for e in full_outputs_list:
            for p in ports:
                if "spt:" + p in e:
                    moned_list.append(e)
                    moned_ports.append(p)
        unmoned_ports = set(ports) - set(moned_ports)
        add_ports_to_mon(unmoned_ports)

        usage = {}
        for o in moned_list:
            so = o.split()
            out = so[1]
            port = so[-1][4:]
            assert_exit(isinstance(port, str), '90')
            usage[port] = int(out)

        for port, out in usage.items():
            assert_exit(isinstance(port, str), '94')
            last = usage_last.get(port, 0)
            if usage_disk[port] == 0:
                usage_disk[port] = out
            if out < last:
                usage_last[port] = out
            if last == 0:
                usage_last[port] = usage_disk[port]
            else:
                diff = out - last
                usage_disk[port] += diff
                usage_last[port] = out

        with open(data_path, 'w') as fd:
            fd.write(json.dumps(usage_disk))
        time.sleep(2)


def get_statistic(port):
    assert_exit(isinstance(port, str), 'get_statistic')
    if not port:
        res = ""
        for p in ports:
            b = usage_disk[p]
            kb = int(b / 1024)
            gb = round(kb / 1024 / 1024, 2)
            rmb = gb
            res += "Port {} data usage: {}KB = {}GB => Bill: {}RMB\n".format(p, kb, gb, rmb)
        return res
    b = usage_disk[port]
    kb = int(b / 1024)
    gb = round(kb / 1024 / 1024, 2)
    rmb = gb
    return "Port {} data usage: {}KB = {}GB => Bill: {}RMB".format(port, kb, gb, rmb)


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    paths = {
        '/': {'status': 200}
    }
    for p in ports:
        paths['/' + p] = {'status': 200}

    def do_GET(self):
        if self.path in self.paths:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(get_statistic(self.path[1:]).encode('utf-8'))
        else:
            self.send_response(404)


jobt = threading.Thread(target=job, name='TrafficMonitorThread')
jobt.start()
httpd = HTTPServer(('0.0.0.0', 9000), SimpleHTTPRequestHandler)
httpd.serve_forever()
