terraform {
  required_version = ">= 1.11.3"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.33.0"
    }
  }
}
