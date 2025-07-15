locals {
  project_id = "pas-production-1"
  region     = "europe-west4"
  zone       = "europe-west4-b"

  required_apis = [
    "compute.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "aiplatform.googleapis.com",
    "container.googleapis.com"
  ]
}

provider "google" {
  project = local.project_id
  region  = local.region
}

resource "google_project_service" "gcp_services" {
  for_each = toset(local.required_apis)
  project  = local.project_id
  service  = each.key
}

resource "google_storage_bucket" "terraform_state" {
  name     = "pas-production-terraform-remote-backend"
  location = local.region

  force_destroy               = false
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

terraform {
  backend "gcs" {
    bucket = "pas-production-terraform-remote-backend"
  }
}

resource "google_compute_network" "pas_network" {
  name                    = "pas-network"
  project                 = local.project_id
  auto_create_subnetworks = false
  mtu                     = 1460
}

resource "google_compute_subnetwork" "pas_subnet" {
  name          = "pas-subnet"
  project       = local.project_id
  ip_cidr_range = "10.0.1.0/24"
  region        = local.region
  network       = google_compute_network.pas_network.id
}
