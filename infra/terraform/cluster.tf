# Local Kubernetes cluster in Docker: one control plane and one worker.
# NodePorts are mapped to localhost so the API, Grafana and Prometheus open in a browser.
resource "kind_cluster" "this" {
  name           = var.cluster_name
  node_image     = var.node_image
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

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

# kind nodes cannot pull an image which only exists on the host, so copy it in.
resource "null_resource" "load_image" {
  count = var.load_local_image ? 1 : 0

  triggers = {
    cluster = kind_cluster.this.id
    image   = var.image
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/../../scripts/load_image_into_kind.sh ${var.image} ${kind_cluster.this.name}"
  }
}
