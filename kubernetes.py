# coding: utf-8

from fabkit import *  # noqa
from fablib.base import SimpleBase


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'

        self.packages = {
            'CentOS .*': [
                'wget',
                'docker',
                'kubernetes',
                'etcd',
            ]
        }

        self.services = {
            'CentOS .*': [
                'etcd',
                'kube-apiserver',
                'kube-controller-manager',
                'kube-scheduler',
                'kube-proxy',
                'kubelet',
                'docker',
            ]
        }

    def init_after(self):
        self.data.update({
            'my_ip': env.node['ip']['default_dev']['ip'],
        })

    def setup(self):
        data = self.init()
        self.install_packages()

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')

        Service('firewalld').stop().disable()

        filer.template('/etc/kubernetes/config', data=data)
        filer.template('/etc/kubernetes/apiserver', data=data)
        filer.template('/etc/kubernetes/kubelet', data=data)
        filer.template('/etc/etcd/etcd.conf', data=data)

        self.restart_services().enable_services()
