resource "google_compute_global_address" "db_private_address" {
  name          = "db-private-ip-address"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.network_link
}

resource "google_service_networking_connection" "db_private_vpc_connection" {
  network                 = var.network_link
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.db_private_address.name]
}

resource "google_sql_database_instance" "postgres" {
  name             = "${var.db_name}-instance"
  database_version = "POSTGRES_17"
  region           = var.region
  project          = var.project_id

  settings {
    tier              = "db-custom-1-4096" # 1 vCPU/4G RAM
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"

    location_preference {
      zone = var.zone
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_link
    }
  }

  deletion_protection = true

  depends_on = [google_compute_global_address.db_private_address]
}

resource "google_sql_database" "database" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "user" {
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  name     = var.db_user
  password = var.db_password
}
