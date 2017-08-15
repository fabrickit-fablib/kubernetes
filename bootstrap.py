# coding: utf-8

import socket
from fabkit import *  # noqa
from fablib.base import SimpleBase


class Bootstrap(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'
        self.data = {}

        self.packages = {
            'CentOS .*': ['wget', 'vim', 'git', 'tcpdump', 'bridge-utils', 'ipset', 'socat']
        }
        self.services = {}

    def setup(self):
        data = self.init()
        # sudo('setenforce 0')
        # filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        # Service('firewalld').stop().disable()
        self.install_packages()
        filer.mkdir('/root/kubernetes-tls-assets')

        if env.host == env.hosts[0]:
            sudo('ip addr show dev eth0 | grep {0}/24 || ip addr add {0}/24 dev eth0'.format(data['vip']))

            etcd_servers = ''
            etcd_initial_cluster = ''
            api_servers = ''
            for index, host in enumerate(env.cluster['node_map']['etcd']['hosts']):
                ip = socket.gethostbyname(host)
                etcd_servers += 'https://{0}:2379,'.format(ip)
                etcd_initial_cluster += 'controller{0}=https://{1}:2380,'.format(index, ip)
                api_servers += 'https://{0}:6443,'.format(ip)

            if not databag.exists('kubernetes.bootstrap_token'):
                bootstrap_token = run("head -c 16 /dev/urandom | od -An -t x | tr -d ' '")
                databag.set('kubernetes.bootstrap_token', str(bootstrap_token))

            etcd_servers = etcd_servers[0:-1]
            etcd_initial_cluster = etcd_initial_cluster[0:-1]
            databag.set('kubernetes.api_servers', api_servers)
            databag.set('kubernetes.etcd_servers', etcd_servers)
            databag.set('kubernetes.etcd_initial_cluster', etcd_initial_cluster)

            if not filer.exists('/usr/bin/cfssl'):
                run('wget https://pkg.cfssl.org/R1.2/cfssl_linux-amd64')
                run('chmod +x cfssl_linux-amd64')
                sudo('mv cfssl_linux-amd64 /usr/bin/cfssl')

            if not filer.exists('/usr/bin/cfssljson'):
                run('wget https://pkg.cfssl.org/R1.2/cfssljson_linux-amd64')
                run('chmod +x cfssljson_linux-amd64')
                sudo('mv cfssljson_linux-amd64 /usr/bin/cfssljson')

            filer.template('/root/kubernetes-tls-assets/ca-config.json')
            filer.template('/root/kubernetes-tls-assets/ca-csr.json')
            filer.template('/root/kubernetes-tls-assets/admin-csr.json')
            filer.template('/root/kubernetes-tls-assets/kube-proxy-csr.json')
            filer.template('/root/kubernetes-tls-assets/kubernetes-csr.json')

            with api.cd('/root/kubernetes-tls-assets'):
                if not (filer.exists('/root/kubernetes-tls-assets/ca.pem') and filer.exists('/root/kubernetes-tls-assets/ca-key.pem')):
                    sudo('cfssl gencert -initca ca-csr.json | cfssljson -bare ca')
                    ca_pem = sudo('cat /root/kubernetes-tls-assets/ca.pem')
                    databag.set('kubernetes.ca_pem', str(ca_pem))

                if not (filer.exists('/root/kubernetes-tls-assets/admin.pem') and filer.exists('/root/kubernetes-tls-assets/admin-key.pem')):
                    sudo('cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json'
                         ' -profile=kubernetes admin-csr.json | cfssljson -bare admin')

                if not (filer.exists('/root/kubernetes-tls-assets/kube-proxy.pem') and filer.exists('/root/kubernetes-tls-assets/kube-proxy-key.pem')):
                    sudo('cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json'
                         ' -profile=kubernetes kube-proxy-csr.json | cfssljson -bare kube-proxy')

                if not (filer.exists('/root/kubernetes-tls-assets/kubernetes.pem') and filer.exists('/root/kubernetes-tls-assets/kubernetes-key.pem')):
                    sudo('cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json'
                         ' -profile=kubernetes kubernetes-csr.json | cfssljson -bare kubernetes')
                    kubernetes_pem = sudo('cat /root/kubernetes-tls-assets/kubernetes.pem')
                    databag.set('kubernetes.kubernetes_pem', str(kubernetes_pem))
                    kubernetes_key_pem = sudo('cat /root/kubernetes-tls-assets/kubernetes-key.pem')
                    databag.set('kubernetes.kubernetes_key_pem', str(kubernetes_key_pem))

        else:
            filer.file('/root/kubernetes-tls-assets/ca.pem', src_str=databag.get('kubernetes.ca_pem'))
            filer.file('/root/kubernetes-tls-assets/kubernetes.pem', src_str=databag.get('kubernetes.kubernetes_pem'))
            filer.file('/root/kubernetes-tls-assets/kubernetes-key.pem', src_str=databag.get('kubernetes.kubernetes_key_pem'))
