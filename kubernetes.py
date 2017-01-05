# coding: utf-8

import time
from fabkit import *  # noqa
from fablib.base import SimpleBase
from fablib.docker import Docker
from fablib.calico import Calico
from flannel import Flannel


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'
        self.data = {
            'version': '1.5.1',
            'cni': {
                'version': '0.3.0',
                'type': 'calico',
                'calico_plugin_version': '1.3.0',
            }
        }

        self.packages = {
            'CentOS .*': []
        }

        self.services = {
            'CentOS .*': [
                'kubelet',
            ]
        }

    def init_after(self):
        self.data.update({
            'hostname': env.host,
            'my_ip': env.node['ip']['default_dev']['ip'],
            'ssl_certs_host_path': '/usr/share/pki/ca-trust-source/anchors',  # if coreos path: /usr/share/ca-certificates  # noqa
            'addons': ['kube-dns', 'kubernetes-dashboard',
                       'heapster', 'monitoring-grafana', 'monitoring-influxdb',
                       'logging']
        })

        self.docker = Docker()
        if self.data['cni']['type'] == 'calico':
            self.cni = Calico()
        elif self.data['cni']['type'] == 'flannel':
            self.cni = Flannel()

    def setup(self):
        data = self.init()

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        Service('firewalld').stop().disable()

        self.docker.setup()

        self.cni.setup()
        if self.data['cni']['type'] == 'calico':
            filer.mkdir('/etc/cni/net.d')
            filer.template('/etc/cni/net.d/10-calico.conf', data=data)

        self.install_packages()
        self.install_kubenetes()
        self.create_tls_assets()

        filer.mkdir('/etc/kubernetes/manifests')
        filer.template('/etc/kubernetes/manifests/kube-proxy.yaml', data=data)
        filer.template('/etc/kubernetes/manifests/fluentd-es.yaml', data=data)

        if env.host == env.cluster['kubernetes']['kube_master']:
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
                sudo('[ -e apiserver.csr ] || openssl req -new -key apiserver-key.pem '
                     ' -out apiserver.csr -subj "/CN=kube-apiserver" -config openssl.cnf')
                sudo('[ -e apiserver.pem ] || openssl x509 -req -in apiserver.csr '
                     ' -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out apiserver.pem -days 365 '
                     ' -extensions v3_req -extfile openssl.cnf')

                sudo('[ -e worker-key.pem ] || openssl genrsa -out worker-key.pem 2048')
                sudo('[ -e worker.csr ] || openssl req -new -key worker-key.pem -out worker.csr '
                     ' -subj "/CN=${WORKER_FQDN}" -config worker-openssl.cnf')
                sudo('[ -e worker.pem ] || openssl x509 -req -in worker.csr '
                     ' -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out worker.pem -days 365 '
                     ' -extensions v3_req -extfile worker-openssl.cnf')

                sudo('chmod 600 *key*')

    def put_samples(self):
        filer.mkdir('/tmp/kubesamples')
        for sample in ['nginx-rc.yaml', 'nginx-svc.yaml']:
            filer.template('/tmp/kubesamples/{0}'.format(sample), src='samples/{0}'.format(sample))

    def install_kubenetes(self):
        data = self.init()

        kubenetes_url = 'https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/'.format(data['version'])  # noqa

        with api.cd('/tmp'):
            for binally in ['hyperkube', 'kubectl',  # kubernetes-client
                            'kubelet', 'kube-proxy',  # kubernetes-node
                            'kube-apiserver', 'kube-scheduler', 'kube-controller-manager',  # kubernetes-master # noqa
                            ]:
                sudo('[ -e /usr/bin/{0} ] || (wget {1}{0}; chmod 755 {0}; mv {0} /usr/bin/)'.format(
                    binally, kubenetes_url))

            # install cni
            filer.mkdir('/opt/cni/bin')
            version = data['cni']['version']
            cni_url = 'https://github.com/containernetworking/cni/releases/download/v{0}/cni-v{0}.tgz'.format(version)  # noqa
            sudo('[ -e /opt/cni/bin/cnitool ] || (wget {0}; tar xf cni-v{1}.tgz -C /opt/cni/bin/)'.format(cni_url, version))  # noqa

            for binally in ['calico', 'calico-ipam']:
                calico_url = 'https://github.com/projectcalico/calico-cni/releases/download/v{0}/{1}'.format(data['cni']['calico_plugin_version'], binally)  # noqa
                sudo('[ -e /opt/cni/bin/{0} ] || (wget {1} && chmod 755 {0} && mv {0} /opt/cni/bin/)'.format(binally, calico_url))  # noqa

        filer.mkdir('/etc/kubernetes')
        filer.mkdir('/etc/kubernetes/ssl')
        filer.mkdir('/var/run/kubernetes')
        filer.mkdir('/var/lib/kubelet')
        for service in ['kubelet', 'kube-proxy',  # kubernetes-node
                        'kube-apiserver', 'kube-controller-manager', 'kube-scheduler'  # kubernetes-master  # noqa
                        ]:
            filer.template('/usr/lib/systemd/system/{0}.service'.format(service),
                           src='services/{0}.service'.format(service), data=data)

        sudo('systemctl daemon-reload')

    def setup_nginx_ingress(self):
        # https://github.com/nginxinc/kubernetes-ingress/tree/master/examples/daemon-set
        data = self.init()
        addon = 'nginx-ingress'
        addon_file = '/etc/kubernetes/addons/{0}.yaml'.format(addon)
        is_change = filer.template(addon_file, data=data)
        sudo('kubectl get pods --all-namespaces | grep {0}'
             ' || kubectl create -f {1}'.format(addon, addon_file))

        if is_change:
            sudo('kubectl apply -f {0}'.format(addon_file))
