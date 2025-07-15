output "bucket_name" {
  value = google_storage_bucket.storage_bucket.name
}

output "bucket_uri" {
  # lifehack
  value = "gs://${google_storage_bucket.storage_bucket.name}"
}
