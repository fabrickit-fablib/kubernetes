# coding: utf-8

from fabkit import *  # noqa
from fablib.base import SimpleBase


class Flannel(SimpleBase):
    def __init__(self):
        self.data_key = 'flannel'
        self.data = {
            'master_host': 'localhost'
        }

        self.packages = {
            'CentOS .*': [
                'flannel'
            ]
        }

        self.services = {
            'CentOS .*': [
                'flanneld',
            ]
        }

    def setup(self):
        data = self.init()

        self.install_packages()

        if filer.template('/etc/sysconfig/flanneld', data=data):
            self.handlers['restart_flanneld'] = True

        if data['master_host'] == env.host:
            filer.template('/tmp/flannel.json')
            run('etcdctl set /atomic.io/network/config < /tmp/flannel.json')

        self.start_services().enable_services()
        self.exec_handlers()
