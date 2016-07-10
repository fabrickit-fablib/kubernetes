# coding: utf-8

from fabkit import *  # noqa
from fablib.base import SimpleBase


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'

        self.packages = {
            'CentOS .*': [
                'git',
                'vim',
                'wget',
                'kubernetes',
                'flannel',
            ]
        }

        self.services = {
            'CentOS .*': [
                'kube-proxy',
                'kubelet',
                'docker',
                'flanneld',
            ]
        }

    def init_before(self):
        if env.host == env.cluster['kubernetes']['kube_master']:
            self.services['CentOS .*'].extend([
                'kube-apiserver',
                'kube-controller-manager',
                'kube-scheduler',
            ])

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

        if filer.template('/etc/kubernetes/config', data=data):
            self.handlers['restart_kube-api-server'] = True
            self.handlers['restart_kube-controller-manager'] = True
            self.handlers['restart_kube-scheduler'] = True
            self.handlers['restart_kube-proxy'] = True
            self.handlers['restart_kube-kubelet'] = True
        if filer.template('/etc/kubernetes/apiserver', data=data):
            self.handlers['restart_kube-api-server'] = True
        if filer.template('/etc/kubernetes/controller-manager', data=data):
            self.handlers['restart_kube-controller-manager'] = True
        if filer.template('/etc/kubernetes/kubelet', data=data):
            self.handlers['restart_kube-kubelet'] = True

        if env.host == env.cluster['kubernetes']['kube_master']:
            filer.template('/tmp/flannel.json')
            run('etcdctl set /atomic.io/network/config < /tmp/flannel.json')
            filer.template('/etc/kubernetes/serviceaccount.key')

        if filer.template('/etc/sysconfig/flanneld', data=data):
            self.handlers['restart_flanneld']

        self.start_services().enable_services()
        self.exec_handlers()
