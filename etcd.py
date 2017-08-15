# coding: utf-8

from fabkit import *  # noqa
from fablib.base import SimpleBase


class Etcd(SimpleBase):
    def __init__(self):
        self.data_key = 'etcd'
        self.data = {
            'version': '3.2.5',
            'initial_cluster_token': 'etcd-cluster-0',
        }

        self.packages = {
            'CentOS .*': [
                'wget',
                'etcd',
            ]
        }

        self.services = {
            'CentOS .*': [
                'etcd',
            ]
        }

    def init_after(self):
        etcd_name = 'default'
        for i, node in enumerate(env['cluster']['node_map']['etcd']['hosts']):
            if node == env.host:
                etcd_name = 'controller{0}'.format(i)

        self.data.update({
            'etcd_name': etcd_name,
            'initial_cluster': databag.get('kubernetes.etcd_initial_cluster'),
        })

    def setup(self):
        data = self.init()
        filer.mkdir('/var/lib/etcd')
        filer.mkdir('/etc/etcd')
        sudo('cp /root/kubernetes-tls-assets/{ca,kubernetes,kubernetes-key}.pem /etc/etcd/')

        with api.cd('/tmp'):
            if not filer.exists('/usr/bin/etcd'):
                run('wget https://github.com/coreos/etcd/releases/download/v{0}/etcd-v{0}-linux-amd64.tar.gz'.format(data['version']))
                run('tar -xvf etcd-v{0}-linux-amd64.tar.gz'.format(data['version']))
                sudo('mv etcd-v{0}-linux-amd64/etcd* /usr/bin/'.format(data['version']))

        filer.template('/etc/systemd/system/etcd.service', data=data)
        sudo('systemctl daemon-reload')
        sudo('systemctl enable etcd')
        sudo('systemctl start etcd')
