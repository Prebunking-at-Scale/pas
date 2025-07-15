resource "google_container_cluster" "primary" {
  name       = var.cluster_name
  location   = var.zone
  project    = var.project_id
  network    = var.network_link
  subnetwork = var.subnetwork_link

  remove_default_node_pool = true
  initial_node_count       = 1

  enable_shielded_nodes = true

  ip_allocation_policy {
    cluster_ipv4_cidr_block  = var.pods_ipv4_cidr_block
    services_ipv4_cidr_block = var.services_ipv4_cidr_block
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  maintenance_policy {
    recurring_window {
      recurrence = "FREQ=WEEKLY;BYDAY=TU"
      start_time = "2025-01-21T00:00:00Z"
      end_time   = "2025-01-21T06:00:00Z"
    }
  }
}

resource "google_container_node_pool" "general" {
  name       = "general"
  cluster    = google_container_cluster.primary.id
  location   = var.zone
  node_count = var.general_node_count

  node_config {
    machine_type = "n2d-standard-2"

    oauth_scopes = [

    ]

    labels = {
      workload = "web-services"
    }
  }
}

resource "google_container_node_pool" "scrapers" {
  name     = "scrapers"
  cluster  = google_container_cluster.primary.id
  location = var.zone

  node_config {
    machine_type = "c4-standard-2"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      workload = "scraping"
    }
  }

  autoscaling {
    min_node_count  = 0
    max_node_count  = var.max_concurrent_scrapers
    location_policy = "ANY"
  }

  lifecycle {
    ignore_changes = [node_config[0].labels]
  }
}


resource "google_container_node_pool" "analysers" {
  name     = "analysers"
  cluster  = google_container_cluster.primary.id
  location = var.zone

  node_config {
    machine_type = "c4-standard-2"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      workload = "analysis"
    }
  }

  autoscaling {
    min_node_count  = 0
    max_node_count  = var.max_concurrent_analysers
    location_policy = "ANY"
  }

  lifecycle {
    ignore_changes = [node_config[0].labels]
  }
}
