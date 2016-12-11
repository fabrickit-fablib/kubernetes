# coding: utf-8

from fabkit import *  # noqa
from fablib.base import SimpleBase


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'

        self.packages = {
            'CentOS .*': [
                'epel-release',
                'git',
                'vim',
                'wget',
                'jq',
                'docker-engine',
                # 'kubernetes',
            ]
        }

        self.services = {
            'CentOS .*': [
                'kube-proxy',
                'kubelet',
            ]
        }

    def init_before(self):
        data = env.cluster[self.data_key]

        if env.host == data['kube_master']:
            self.services['CentOS .*'].extend([
                'kube-apiserver',
                'kube-controller-manager',
                'kube-scheduler',
            ])

        self.network = data['network']
        if self.network['type'] == 'flannel':
            self.services['CentOS .*'].extend([
                'flanneld'
            ])

            self.packages['CentOS .*'].extend([
                'flannel'
            ])

    def init_after(self):
        self.data.update({
            'my_ip': env.node['ip']['default_dev']['ip'],
        })

    def setup(self):
        data = self.init()

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        Service('firewalld').stop().disable()

        filer.template('/etc/yum.repos.d/docker.repo', data=data)
        self.install_packages()
        self.install_kubenetes()

        Service('docker').start().enable()
        self.setup_network()

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
            filer.template('/etc/kubernetes/serviceaccount.key')

        self.start_services().enable_services()
        self.exec_handlers()

        self.put_samples()

    def put_samples(self):
        filer.mkdir('/tmp/kubesamples')
        for sample in ['nginx-rc.yaml', 'nginx-svc.yaml']:
            filer.template('/tmp/kubesamples/{0}'.format(sample), src='samples/{0}'.format(sample))

    def install_kubenetes(self, version='1.4.7'):
        user.add('kube', group='kube')

        kubenetes_url = 'https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/'.format(version)  # noqa
        with api.cd('/tmp'):
            for binally in ['hyperkube', 'kubectl',  # kubernetes-client
                            'kubelet', 'kube-proxy',  # kubernetes-node
                            'kube-apiserver', 'kube-scheduler', 'kube-controller-manager',  # kubernetes-master # noqa
                            ]:
                sudo('[ -e /usr/bin/{0} ] || (wget {1}{0}; chmod 755 {0}; mv {0} /usr/bin/)'.format(
                    binally, kubenetes_url))

            cni_url = 'https://github.com/containernetworking/cni/releases/download/v0.3.0/cni-v0.3.0.tgz'  # noqa
            sudo('[ -e /usr/bin/cnitool ] || (wget {0}; tar xf cni-v0.3.0.tgz -C /usr/bin/)'.format(
                cni_url))

        filer.mkdir('/etc/kubernetes', owner='kube:kube')
        filer.mkdir('/etc/kubernetes/ssl', owner='kube:kube')
        filer.mkdir('/var/run/kubernetes', owner='kube:kube')
        filer.mkdir('/var/lib/kubelet', owner='kube:kube')
        for service in ['kubelet', 'kube-proxy',  # kubernetes-node
                        'kube-apiserver', 'kube-controller-manager', 'kube-scheduler'  # kubernetes-master  # noqa
                        ]:
            filer.template('/usr/lib/systemd/system/{0}.service'.format(service),
                           src='services/{0}.service'.format(service))

        sudo('systemctl daemon-reload')

    def setup_network(self):
        data = self.init()
        if self.network['type'] == 'flannel':
            if env.host == env.cluster['kubernetes']['kube_master']:
                filer.template('/tmp/flannel.json')
                run('etcdctl set /atomic.io/network/config < /tmp/flannel.json')

            if filer.template('/etc/sysconfig/flanneld', data=data):
                self.handlers['restart_flanneld'] = True

        elif self.network['type'] == 'calico':

            with api.warn_only():
                result = sudo('calicoctl node show | grep {0}'.format(
                    env.node['ip']['default_dev']['ip']))

            if result.return_code != 0:
                with api.cd('/tmp'):
                    sudo('wget https://github.com/projectcalico/calico-containers/releases/download/v0.19.0/calicoctl')  # noqa
                    sudo('chmod 755 calicoctl')
                    sudo('mv calicoctl /usr/bin/')
                    sudo('wget https://github.com/projectcalico/calico-cni/releases/download/v1.3.0/calico')  # noqa
                    sudo('chmod 755 calico')
                    sudo('mv calico /usr/bin/')

                sudo('ETCD_AUTHORITY=127.0.0.1:2379; calicoctl node --ip={0}'.format(
                    env.node['ip']['default_dev']['ip']))
                sudo('calicoctl node show')

            filer.mkdir('/etc/cni/net.d')
            filer.template('/etc/cni/net.d/10-calico.conf', data=data)
