resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name = "monitoring"
  }
}

# metrics-server feeds CPU usage to the Horizontal Pod Autoscaler. kind does not ship it.
resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  version    = "3.12.2"
  namespace  = "kube-system"

  values = [yamlencode({
    args = ["--kubelet-insecure-tls"] # kind kubelets use self-signed certificates
  })]
}

# Prometheus, Alertmanager, Grafana, kube-state-metrics and node-exporter in one chart.
resource "helm_release" "kube_prometheus_stack" {
  name       = "monitoring"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = var.kube_prometheus_stack_version
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name
  timeout    = 900

  values = [yamlencode({
    grafana = {
      adminPassword = var.grafana_admin_password
      service       = { type = "NodePort", nodePort = 30030 }
      sidecar       = { dashboards = { enabled = true, label = "grafana_dashboard", searchNamespace = "ALL" } }
    }

    prometheus = {
      service = { type = "NodePort", nodePort = 30090 }
      prometheusSpec = {
        # pick up ServiceMonitors and rules from any namespace, not only this release
        serviceMonitorSelectorNilUsesHelmValues = false
        ruleSelectorNilUsesHelmValues           = false
        retention                               = "7d"
      }
      additionalServiceMonitors = [{
        name              = "energy-api"
        selector          = { matchLabels = { app = "energy-api" } }
        namespaceSelector = { matchNames = ["energy"] }
        endpoints         = [{ port = "http", path = "/metrics", interval = "15s" }]
      }]
    }

    # the same rules file promtool tests in CI
    additionalPrometheusRulesMap = {
      energy-api = yamldecode(file("${path.module}/../../monitoring/alert-rules.yaml"))
    }
  })]
}

# Grafana's sidecar loads any ConfigMap labelled grafana_dashboard=1 as a dashboard.
resource "kubernetes_config_map_v1" "energy_dashboard" {
  metadata {
    name      = "energy-api-dashboard"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { grafana_dashboard = "1" }
  }

  data = {
    "energy-api.json" = file("${path.module}/../../monitoring/dashboards/energy-api.json")
  }

  depends_on = [helm_release.kube_prometheus_stack]
}
