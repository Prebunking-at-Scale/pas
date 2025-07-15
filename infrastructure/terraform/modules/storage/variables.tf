variable "project_id" {
  type = string
}

variable "bucket_name" {
  type        = string
  description = "globally unique bucket name"
}

variable "region" {
  type    = string
  default = "europe-west4"
}

variable "public_access_prevention" {
  type    = string
  default = "inherited"
}

variable "enable_versioning" {
  type        = bool
  description = "enable bucket versioning (might be desirable on prod)"
  default     = false
}
