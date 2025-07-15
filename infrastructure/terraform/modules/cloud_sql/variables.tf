variable "network_link" {
  type        = string
  description = "the self_link of the network to peer the db into"
}

variable "db_name" {
  type = string
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "db_user" {
  type    = string
  default = "prebunker"
}

variable "db_password" {
  type = string
}
