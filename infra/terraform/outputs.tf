output "api_url" {
  description = "Forecast API (try /health and /docs)"
  value       = "http://localhost:30080"
}

output "grafana_url" {
  description = "Grafana. Log in as admin with grafana_admin_password. Dashboard: Energy Forecast API."
  value       = "http://localhost:30030"
}

output "prometheus_url" {
  description = "Prometheus UI, including the Alerts page"
  value       = "http://localhost:30090"
}

output "kubeconfig_path" {
  description = "Use with: export KUBECONFIG=$(terraform output -raw kubeconfig_path)"
  value       = kind_cluster.this.kubeconfig_path
}
