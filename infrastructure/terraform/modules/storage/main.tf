resource "google_storage_bucket" "storage_bucket" {
  name                        = var.bucket_name # "pas-prototyping-storage"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = var.public_access_prevention
  force_destroy               = false # safety

  versioning {
    enabled = var.enable_versioning
  }
}

