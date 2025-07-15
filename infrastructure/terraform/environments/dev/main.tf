locals {
  required_apis = [
    "compute.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "aiplatform.googleapis.com",
    "container.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ]
}

provider "google" {
  project = var.project_id
  region  = var.region
}

terraform {
  backend "gcs" {
    bucket = "pas-development-terraform-remote-backend"
  }
}

module "terraform_state" {
  # the bucket_name here should be the same as the terraform backend.
  source                   = "../../modules/storage"
  bucket_name              = "pas-development-terraform-remote-backend"
  project_id               = var.project_id
  region                   = var.region
  public_access_prevention = "enforced"
  enable_versioning        = true
}

module "pas_prototyping_storage" {
  source      = "../../modules/storage"
  bucket_name = "pas-prototyping-storage"
  project_id  = var.project_id
  region      = var.region
}

module "postgresql_db" {
  source       = "../../modules/cloud_sql"
  db_name      = "pas-vectordb"
  project_id   = var.project_id
  region       = var.region
  zone         = var.zone
  network_link = google_compute_network.pas_network.self_link

  db_user     = "prebunker"
  db_password = var.db_password
}

module "dev-cluster" {
  source          = "../../modules/gke"
  cluster_name    = "dev-cluster"
  project_id      = var.project_id
  zone            = var.zone
  network_link    = google_compute_network.pas_network.self_link
  subnetwork_link = google_compute_subnetwork.pas_subnet.self_link
}

resource "google_project_service" "gcp_services" {
  for_each = toset(local.required_apis)
  project  = var.project_id
  service  = each.key
}

resource "google_compute_network" "pas_network" {
  name                    = "pas-network"
  project                 = var.project_id
  auto_create_subnetworks = false
  mtu                     = 1460
}

resource "google_compute_subnetwork" "pas_subnet" {
  name          = "pas-subnet"
  project       = var.project_id
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.pas_network.id
}
