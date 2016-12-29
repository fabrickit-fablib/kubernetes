# coding: utf-8

import time
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
            'hostname': env.host,
            'my_ip': env.node['ip']['default_dev']['ip'],
            'ssl_certs_host_path': '/usr/share/pki/ca-trust-source/anchors',  # if coreos path: /usr/share/ca-certificates  # noqa
            'addons': ['kube-dns', 'kubernetes-dashboard',
                       'heapster', 'monitoring-grafana', 'monitoring-influxdb',
                       'logging']
        })

    def setup(self):
        data = self.init()

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        Service('firewalld').stop().disable()

        filer.template('/etc/yum.repos.d/docker.repo', data=data)
        self.install_packages()
        self.install_kubenetes()
        self.create_tls_assets()

        Service('docker').start().enable()
        self.setup_network()

        filer.mkdir('/etc/kubernetes/manifests')
        filer.template('/etc/kubernetes/manifests/kube-proxy.yaml', data=data)
        filer.template('/etc/kubernetes/manifests/fluentd-es.yaml', data=data)

        if env.host == env.cluster['kubernetes']['kube_master']:
            # filer.template('/etc/kubernetes/serviceaccount.key')
            filer.template('/etc/kubernetes/ssl/serviceaccount.key')
            filer.template('/etc/kubernetes/manifests/kube-apiserver.yaml', data=data)
            filer.template('/etc/kubernetes/manifests/kube-controller-manager.yaml', data=data)
            filer.template('/etc/kubernetes/manifests/kube-scheduler.yaml', data=data)

        Service('kubelet').start().enable()

        if env.host == env.cluster['kubernetes']['kube_master']:
            for count in range(10):
                with api.warn_only():
                    result = run('curl http://localhost:8080/version')
                    if result.return_code == 0:
                        break

                    time.sleep(100)

            filer.mkdir('/etc/kubernetes/addons')
            for addon in data['addons']:
                addon_file = '/etc/kubernetes/addons/{0}.yaml'.format(addon)
                is_change = filer.template(addon_file, data=data)
                sudo('kubectl get services --namespace kube-system | grep {0}'
                     ' || kubectl create -f {1}'.format(addon, addon_file))
                if is_change:
                    sudo('kubectl apply -f {0}'.format(addon_file))

        return

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
            # filer.template('/etc/kubernetes/serviceaccount.key')
            filer.template('/etc/kubernetes/ssl/serviceaccount.key')
            filer.mkdir('/etc/kubernetes/manifests')
            filer.template('/etc/kubernetes/manifests/kube-apiserver.yaml')

        return

        self.start_services().enable_services()
        self.exec_handlers()

        self.put_samples()

    def create_tls_assets(self):
        # https://coreos.com/kubernetes/docs/latest/openssl.html
        data = self.init()
        filer.template('/etc/kubernetes/ssl/openssl.cnf')
        filer.template('/etc/kubernetes/ssl/worker-openssl.cnf')

        with api.cd('/etc/kubernetes/ssl'):
            with api.shell_env(MASTER_HOST=data['kube_master'],
                               K8S_SERVICE_IP=data['k8s_service_ip'],
                               WORKER_IP=env.host,
                               WORKER_FQDN=env.host):

                filer.template('/etc/kubernetes/ssl/ca.pem')
                filer.template('/etc/kubernetes/ssl/ca-key.pem')
                sudo('cp ca.pem /usr/share/pki/ca-trust-source/anchors/ca.pem')
                sudo('update-ca-trust extract')

                sudo('[ -e apiserver-key.pem ] || openssl genrsa -out apiserver-key.pem 2048')
                sudo('[ -e apiserver.csr ] || openssl req -new -key apiserver-key.pem -out apiserver.csr -subj "/CN=kube-apiserver" -config openssl.cnf')
                sudo('[ -e apiserver.pem ] || openssl x509 -req -in apiserver.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out apiserver.pem -days 365 -extensions v3_req -extfile openssl.cnf')

                sudo('[ -e worker-key.pem ] || openssl genrsa -out worker-key.pem 2048')
                sudo('[ -e worker.csr ] || openssl req -new -key worker-key.pem -out worker.csr -subj "/CN=${WORKER_FQDN}" -config worker-openssl.cnf')
                sudo('[ -e worker.pem ] || openssl x509 -req -in worker.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out worker.pem -days 365 -extensions v3_req -extfile worker-openssl.cnf')

                sudo('chmod 600 *key*')

    def put_samples(self):
        filer.mkdir('/tmp/kubesamples')
        for sample in ['nginx-rc.yaml', 'nginx-svc.yaml']:
            filer.template('/tmp/kubesamples/{0}'.format(sample), src='samples/{0}'.format(sample))

    def install_kubenetes(self):
        data = self.init()
        user.add('kube', group='kube')

        kubenetes_url = 'https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/'.format(data['version'])  # noqa

        with api.cd('/tmp'):
            for binally in ['hyperkube', 'kubectl',  # kubernetes-client
                            'kubelet', 'kube-proxy',  # kubernetes-node
                            'kube-apiserver', 'kube-scheduler', 'kube-controller-manager',  # kubernetes-master # noqa
                            ]:
                sudo('[ -e /usr/bin/{0} ] || (wget {1}{0}; chmod 755 {0}; mv {0} /usr/bin/)'.format(
                    binally, kubenetes_url))

            filer.mkdir('/opt/cni/bin')
            cni_url = 'https://github.com/containernetworking/cni/releases/download/v0.3.0/cni-v0.3.0.tgz'  # noqa
            sudo('[ -e /opt/cni/bin/cnitool ] || (wget {0}; tar xf cni-v0.3.0.tgz -C /opt/cni/bin/)'.format(cni_url))

        filer.mkdir('/etc/kubernetes', owner='kube:kube')
        filer.mkdir('/etc/kubernetes/ssl', owner='kube:kube')
        filer.mkdir('/var/run/kubernetes', owner='kube:kube')
        filer.mkdir('/var/lib/kubelet', owner='kube:kube')
        for service in ['kubelet', 'kube-proxy',  # kubernetes-node
                        'kube-apiserver', 'kube-controller-manager', 'kube-scheduler'  # kubernetes-master  # noqa
                        ]:
            filer.template('/usr/lib/systemd/system/{0}.service'.format(service),
                           src='services/{0}.service'.format(service), data=data)

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
                result = sudo('/opt/cni/bin/calicoctl node show | grep {0}'.format(
                    env.node['ip']['default_dev']['ip']))

            if result.return_code != 0:
                with api.cd('/tmp'):
                    sudo('wget https://github.com/projectcalico/calico-containers/releases/download/v0.19.0/calicoctl')  # noqa
                    sudo('chmod 755 calicoctl')
                    sudo('mv calicoctl /opt/cni/bin/')
                    sudo('wget https://github.com/projectcalico/calico-cni/releases/download/v1.3.0/calico')  # noqa
                    sudo('chmod 755 calico')
                    sudo('mv calico /opt/cni/bin/')

                sudo('ETCD_AUTHORITY=127.0.0.1:2379; /opt/cni/bin/calicoctl node --ip={0}'.format(
                    env.node['ip']['default_dev']['ip']))
                sudo('/opt/cni/bin/calicoctl node show')

            filer.mkdir('/etc/cni/net.d')
            filer.template('/etc/cni/net.d/10-calico.conf', data=data)
