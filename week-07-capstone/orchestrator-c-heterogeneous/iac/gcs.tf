provider "google" {
  credentials = file("gcp-sa-key.json")
  project     = "cse636-capstone-iac"
  region      = var.region
}

variable "region" {
  description = "GCS bucket location"
  type        = string
  default     = "US"
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "cse636-capstone-iac"
}

resource "google_storage_bucket" "capstone_artifacts" {
  name     = "capstone-artifacts"
  location = var.region
  project  = var.project_id

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true

  public_access_prevention = "enforced"

  labels = {
    environment = "capstone"
    managed_by  = "terraform"
  }
}
