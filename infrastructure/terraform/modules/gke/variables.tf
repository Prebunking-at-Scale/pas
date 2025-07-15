variable "cluster_name" {
  type = string
}

variable "zone" {
  type = string
}

variable "project_id" {
  type = string
}

variable "network_link" {
  type = string
}

variable "subnetwork_link" {
  type = string
}

variable "pods_ipv4_cidr_block" {
  type    = string
  default = ""
}

variable "services_ipv4_cidr_block" {
  type    = string
  default = ""
}

variable "general_node_count" {
  type    = number
  default = 1
}

variable "max_concurrent_scrapers" {
  type    = number
  default = 1
}

variable "max_concurrent_analysers" {
  type    = number
  default = 1
}
