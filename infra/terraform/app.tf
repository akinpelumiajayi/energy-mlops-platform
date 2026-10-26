locals {
  app_labels = { app = "energy-api" }
}

resource "kubernetes_namespace_v1" "energy" {
  metadata {
    name = "energy"
  }
}

resource "kubernetes_deployment_v1" "api" {
  metadata {
    name      = "energy-api"
    namespace = kubernetes_namespace_v1.energy.metadata[0].name
    labels    = local.app_labels
  }

  spec {
    replicas = var.api_replicas

    selector {
      match_labels = local.app_labels
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
        max_surge       = "1"
      }
    }

    template {
      metadata {
        labels = local.app_labels
      }

      spec {
        security_context {
          run_as_non_root = true
          run_as_user     = 10001
        }

        container {
          name              = "api"
          image             = var.image
          image_pull_policy = "Always" # re-pull from the local registry on every rollout

          port {
            name           = "http"
            container_port = 8000
          }

          resources {
            requests = { cpu = "100m", memory = "256Mi" }
            limits   = { cpu = "500m", memory = "512Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = "http"
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = "http"
            }
            initial_delay_seconds = 15
            period_seconds        = 10
          }

          security_context {
            allow_privilege_escalation = false
            read_only_root_filesystem  = true
            capabilities {
              drop = ["ALL"]
            }
          }
        }
      }
    }
  }

  depends_on = [null_resource.connect_registry]
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "energy-api"
    namespace = kubernetes_namespace_v1.energy.metadata[0].name
    labels    = local.app_labels
  }

  spec {
    type     = "NodePort"
    selector = local.app_labels

    port {
      name        = "http"
      port        = 8000
      target_port = "http"
      node_port   = 30080
    }
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "api" {
  metadata {
    name      = "energy-api"
    namespace = kubernetes_namespace_v1.energy.metadata[0].name
  }

  spec {
    min_replicas = var.api_replicas
    max_replicas = var.api_max_replicas

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.api.metadata[0].name
    }

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }
  }

  depends_on = [helm_release.metrics_server]
}

# Keep at least one pod serving during node drains and upgrades.
resource "kubernetes_pod_disruption_budget_v1" "api" {
  metadata {
    name      = "energy-api"
    namespace = kubernetes_namespace_v1.energy.metadata[0].name
  }

  spec {
    min_available = "1"
    selector {
      match_labels = local.app_labels
    }
  }
}
