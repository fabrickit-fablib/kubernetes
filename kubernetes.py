# coding: utf-8

import time
from fabkit import *  # noqa
from fablib.base import SimpleBase
from fablib.docker import Docker


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'
        self.data = {
            'service_cluster_ip_range': '10.32.0.0/16',
            'cluster_dns': '10.32.0.10',
            'cluster_cidr': '10.200.0.0/16',
            'version': '1.7.3',
            'cni': {
                'version': '0.5.2',
                'type': 'calico',
                'calico_plugin_version': '1.3.0',
                'calico_version': '1.0.0',
            },
            'helm': {
                'version': '2.5.1',
            },
            'tiller': {
                'version': '2.5.1',
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
            'bootstrap_token': databag.get('kubernetes.bootstrap_token'),
            'etcd_servers': databag.get('kubernetes.etcd_servers'),
            'certificate_aythority_data': databag.get('kubernetes.certificate_aythority_data'),
            'api_servers': databag.get('kubernetes.api_servers'),

            'hostname': env.host,
            'my_ip': env.node['ip']['default_dev']['ip'],
            'ssl_certs_host_path': '/usr/share/pki/ca-trust-source/anchors',  # if coreos path: /usr/share/ca-certificates  # noqa
            'addons': ['kube-proxy', 'kube-dns', 'kubernetes-dashboard',
                       'heapster', 'monitoring-grafana', 'monitoring-influxdb',
                       'logging-es', 'logging-kibana', 'fluentd-es', 'tiller-deploy',
                       'prometheus', 'prometheus-node-exporter']
        })

        self.docker = Docker()

    def setup(self):
        data = self.init()
        filer.mkdir('/var/lib/kubernetes/')
        filer.mkdir('/var/run/kubernetes/')
        filer.mkdir('/var/lib/kubelet/')
        filer.mkdir('/var/lib/kube-proxy/')
        filer.mkdir('/etc/kubernetes/')
        filer.mkdir('/etc/kubernetes/addons')

        with api.cd('/tmp'):
            for binary in ['kubectl', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler', 'kube-proxy', 'kubelet']:
                if not filer.exists('/usr/bin/{0}'.format(binary)):
                    run('wget https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/{1}'.format(data['version'], binary))
                    sudo('chmod 755 {0}'.format(binary))
                    sudo('cp {0} /usr/bin/'.format(binary))

            if not filer.exists('/usr/bin/docker'):
                run('wget https://get.docker.com/builds/Linux/x86_64/docker-1.12.6.tgz')
                run('tar -xvf docker-1.12.6.tgz')
                sudo('mv docker/docker* /usr/bin/')

            if not filer.exists('/opt/cni'):
                filer.mkdir('/opt/cni')
                run('wget https://storage.googleapis.com/kubernetes-release/network-plugins/cni-amd64-0799f5732f2a11b329d9e3d51b9c8f2e3759f2ff.tar.gz')
                sudo('tar -xvf cni-amd64-0799f5732f2a11b329d9e3d51b9c8f2e3759f2ff.tar.gz -C /opt/cni')

        filer.template('/var/lib/kubernetes/token.csv', data=data)
        sudo('cp /root/kubernetes-tls-assets/{ca,kubernetes,kubernetes-key}.pem /var/lib/kubernetes/')

        filer.template('/etc/systemd/system/kube-apiserver.service', data=data)
        filer.template('/etc/systemd/system/kube-controller-manager.service', data=data)
        filer.template('/etc/systemd/system/kube-scheduler.service', data=data)
        filer.template('/etc/systemd/system/kubelet.service', data=data)
        filer.template('/etc/systemd/system/kube-proxy.service', data=data)
        filer.template('/etc/systemd/system/docker.service', data=data)
        sudo('systemctl daemon-reload')
        sudo('systemctl start docker')

        if env.host == env.hosts[0]:
            sudo('systemctl start kube-apiserver')
            sudo('systemctl start kube-controller-manager')
            sudo('systemctl start kube-scheduler')
            sudo('cp /root/kubernetes-tls-assets/ca-key.pem /var/lib/kubernetes/')

            if not filer.exists('/root/kubeconfigs'):
                filer.mkdir('/root/kubeconfigs')

                sudo('kubectl config set-cluster kubernetes-the-hard-way'
                     ' --certificate-authority=/var/lib/kubernetes/ca.pem'
                     ' --embed-certs=true'
                     ' --server=https://{0}:6443'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig'.format(env['node']['ip']['default_dev']['ip']))

                sudo('kubectl config set-credentials kubelet-bootstrap'
                     ' --token={0}'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig'.format(data['bootstrap_token']))

                sudo('kubectl config set-context default'
                     ' --cluster=kubernetes-the-hard-way'
                     ' --user=kubelet-bootstrap'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig')

                sudo('kubectl config use-context default --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig')

                sudo('kubectl config set-cluster kubernetes-the-hard-way'
                     ' --certificate-authority=/var/lib/kubernetes/ca.pem'
                     ' --embed-certs=true'
                     ' --server=https://{0}:6443'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig'.format(env['node']['ip']['default_dev']['ip']))

                sudo('kubectl config set-credentials kube-proxy'
                     ' --client-certificate=/root/kubernetes-tls-assets/kube-proxy.pem'
                     ' --client-key=/root/kubernetes-tls-assets/kube-proxy-key.pem'
                     ' --embed-certs=true'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                sudo('kubectl config set-context default'
                     ' --cluster=kubernetes-the-hard-way'
                     ' --user=kube-proxy'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                sudo('kubectl config use-context default --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                bootstrap_kubeconfig = sudo('cat /root/kubeconfigs/bootstrap.kubeconfig')
                databag.set('kubernetes.bootstrap_kubeconfig', str(bootstrap_kubeconfig))
                kube_proxy_kubeconfig = sudo('cat /root/kubeconfigs/kube-proxy.kubeconfig')
                databag.set('kubernetes.kube_proxy_kubeconfig', str(kube_proxy_kubeconfig))
                with api.warn_only():
                    while True:
                        result = run('ss -ln | grep ":6443 "')
                        if result.return_code == 0:
                            break
                        time.sleep(10)

                run('kubectl create clusterrolebinding kubelet-bootstrap --clusterrole=system:node-bootstrapper --user=kubelet-bootstrap')

        bootstrap_kubeconfig = databag.get('kubernetes.bootstrap_kubeconfig')
        kube_proxy_kubeconfig = databag.get('kubernetes.kube_proxy_kubeconfig')
        filer.file('/var/lib/kubelet/bootstrap.kubeconfig', src_str=bootstrap_kubeconfig)
        filer.file('/var/lib/kube-proxy/kube-proxy.kubeconfig', src_str=kube_proxy_kubeconfig)
        sudo('systemctl start kubelet')
        sudo('systemctl start kube-proxy')

        return

        sudo('setenforce 0')
        filer.Editor('/etc/selinux/config').s('SELINUX=enforcing', 'SELINUX=disable')
        Service('firewalld').stop().disable()
        # sudo('sysctl -w net.bridge.bridge-nf-call-iptables=1')

        self.docker.setup()

        self.install_packages()
        self.install_kubenetes()
        # self.create_tls_assets()

        if env.host == env.cluster['kubernetes']['kube_master']:
            filer.template('/etc/kubernetes/ssl/serviceaccount.key')
            filer.mkdir('/etc/kubernetes/manifests')
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

            return

            self.setup_calico()

            filer.mkdir('/etc/kubernetes/addons')
            for addon in data['addons']:
                addon_file = '/etc/kubernetes/addons/{0}.yaml'.format(addon)
                filer.template(addon_file, data=data)
                sudo('kubectl apply -f {0}'.format(addon_file))

    def approve_certificate(self):
        data = self.init()
        run("for csr in `kubectl get csr | grep Pending | awk '{print $1}'`; do kubectl certificate approve $csr; done")

        sudo('kubectl get secret calico-etcd-secrets -n kube-system'
             ' || kubectl create secret generic calico-etcd-secrets -n kube-system'
             ' --from-file=etcd-key=/etc/etcd/kubernetes-key.pem'
             ' --from-file=etcd-cert=/etc/etcd/kubernetes.pem'
             ' --from-file=etcd-ca=/etc/etcd/ca.pem')
        filer.template('/etc/kubernetes/addons/calico.yaml', data=data)
        run('kubectl apply -f /etc/kubernetes/addons/calico.yaml')
