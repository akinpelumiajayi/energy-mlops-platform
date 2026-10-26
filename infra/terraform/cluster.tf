# Local Kubernetes cluster in Docker: one control plane and one worker.
# NodePorts are mapped to localhost so the API, Grafana and Prometheus open in a browser.
resource "kind_cluster" "this" {
  name           = var.cluster_name
  node_image     = var.node_image
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    # Pull localhost:5001/* images from the local registry container (scripts/start_registry.sh)
    containerd_config_patches = [
      <<-TOML
      [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5001"]
        endpoint = ["http://${var.registry_name}:5000"]
      TOML
    ]

    node {
      role = "control-plane"

      extra_port_mappings {
        container_port = 30080 # forecast API
        host_port      = 30080
      }
      extra_port_mappings {
        container_port = 30030 # Grafana
        host_port      = 30030
      }
      extra_port_mappings {
        container_port = 30090 # Prometheus
        host_port      = 30090
      }
    }

    node {
      role = "worker"
    }
  }
}

# Attach the local registry container to the kind Docker network so nodes can reach it.
resource "null_resource" "connect_registry" {
  triggers = {
    cluster  = kind_cluster.this.id
    registry = var.registry_name
  }

  provisioner "local-exec" {
    command = "docker network connect kind ${var.registry_name} 2>/dev/null || true"
  }
}
