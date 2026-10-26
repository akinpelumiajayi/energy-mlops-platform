variable "cluster_name" {
  description = "Name of the local kind cluster"
  type        = string
  default     = "energy-mlops"
}

variable "node_image" {
  description = "kindest/node image, pins the Kubernetes version. null uses the provider default."
  type        = string
  default     = null
}

variable "image" {
  description = "Container image for the forecast API"
  type        = string
  default     = "energy-api:local"
}

variable "load_local_image" {
  description = "Load a locally built image into kind. Set false when pulling from a registry."
  type        = bool
  default     = true
}

variable "api_replicas" {
  description = "Starting number of API pods. The HPA scales between this and api_max_replicas."
  type        = number
  default     = 2

  validation {
    condition     = var.api_replicas >= 1 && var.api_replicas <= 10
    error_message = "api_replicas must be between 1 and 10."
  }
}

variable "api_max_replicas" {
  description = "Upper limit for the Horizontal Pod Autoscaler"
  type        = number
  default     = 5
}

variable "kube_prometheus_stack_version" {
  description = "Version of the prometheus-community/kube-prometheus-stack Helm chart"
  type        = string
  default     = "65.5.0"
}

variable "grafana_admin_password" {
  description = "Grafana admin password. Set it in terraform.tfvars or TF_VAR_grafana_admin_password."
  type        = string
  sensitive   = true
}
