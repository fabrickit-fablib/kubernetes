# coding: utf-8

import time
from fabkit import *  # noqa
from fablib.base import SimpleBase
from fablib.docker import Docker


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'
        self.data = {
            'version': '1.5.1',
            'cni': {
                'version': '0.3.0',
                'type': 'calico',
                'calico_plugin_version': '1.3.0',
                'calico_version': '1.0.0',
            },
            'helm': {
                'version': '2.1.3',
            },
            'tiller': {
                'version': '2.1.3',
            },
        }

        self.packages = {
            'CentOS .*': ['socat']
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
                       'logging', 'fluentd-es', 'tiller-deploy', 'prometheus']
        })

        self.docker = Docker()

    def setup(self):
        data = self.init()

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        Service('firewalld').stop().disable()

        self.docker.setup()

        # self.cni.setup()
        # if self.data['cni']['type'] == 'calico':
        #     filer.mkdir('/etc/cni/net.d')
        #     filer.template('/etc/cni/net.d/10-calico.conf', data=data)

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

            self.setup_calico()

            filer.mkdir('/etc/kubernetes/addons')
            for addon in data['addons']:
                addon_file = '/etc/kubernetes/addons/{0}.yaml'.format(addon)
                filer.template(addon_file, data=data)
                sudo('kubectl apply -f {0}'.format(addon_file))

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

    def install_kubenetes(self):
        data = self.init()

        kubenetes_url = 'https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/'.format(data['version'])  # noqa

        with api.cd('/tmp'):
            for binally in ['kubectl', 'kubelet']:
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

            # install helm
            sudo('[ -e /usr/bin/helm ]'
                 ' || (wget http://storage.googleapis.com/kubernetes-helm/helm-v{0}-linux-amd64.tar.gz'  # noqa
                 ' && tar xf helm-v{0}-linux-amd64.tar.gz && mv linux-amd64/helm /usr/bin/)'.format(
                 data['helm']['version']))

        filer.mkdir('/etc/kubernetes')
        filer.mkdir('/etc/kubernetes/ssl')
        filer.mkdir('/var/run/kubernetes')
        filer.mkdir('/var/lib/kubelet')
        for service in ['kubelet']:
            filer.template('/usr/lib/systemd/system/{0}.service'.format(service),
                           src='services/{0}.service'.format(service), data=data)

        sudo('systemctl daemon-reload')

        calicoctl_url = 'https://github.com/projectcalico/calico-containers/releases/download/v{0}/calicoctl'.format(data['cni']['calico_version'])  # noqa
        calicoctl_path = '/usr/bin/calicoctl'
        if not filer.exists(calicoctl_path):
            with api.cd('/tmp'):
                sudo('wget {0}'.format(calicoctl_url))
                sudo('chmod 755 calicoctl')
                sudo('mv calicoctl {0}'.format(calicoctl_path))

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

    def setup_calico(self):
        data = self.init()
        filer.mkdir('/etc/kubernetes/addons')
        addon_file = '/etc/kubernetes/addons/calico.yaml'
        is_change = filer.template(addon_file, data=data)
        sudo('kubectl get ds --namespace kube-system | grep calico-node'
             ' || kubectl create -f {0}'.format(addon_file))

        if is_change:
            sudo('kubectl apply -f {0}'.format(addon_file))

        for count in range(10):
            with api.warn_only():
                result = sudo('calicoctl node status')
                if result.return_code == 0:
                    break

                time.sleep(100)
