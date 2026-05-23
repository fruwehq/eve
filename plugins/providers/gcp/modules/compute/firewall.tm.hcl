generate_hcl "z_gcp_firewall.tf" {
  content {
    variable "profile_name" {
      type        = string
      description = "Instance/profile name used for firewall naming"
    }

    variable "ssh_allowed_cidr" {
      type        = string
      description = "CIDR allowed to reach SSH"
    }

    variable "bundle_packages" {
      type        = string
      default     = "ssh"
      description = "Comma-separated package list"
    }

    data "google_compute_network" "default" {
      name = "default"
    }

    locals {
      gcp_name    = substr(replace(lower(var.profile_name), "_", "-"), 0, 52)
      package_set = toset(split(",", var.bundle_packages))
    }

    resource "google_compute_firewall" "ssh" {
      name          = "${local.gcp_name}-ssh"
      network       = data.google_compute_network.default.name
      source_ranges = [var.ssh_allowed_cidr]
      target_tags   = [local.gcp_name]

      allow {
        protocol = "tcp"
        ports    = ["22"]
      }
    }

    resource "google_compute_firewall" "thinlinc" {
      count         = contains(local.package_set, "thinlinc") ? 1 : 0
      name          = "${local.gcp_name}-thinlinc"
      network       = data.google_compute_network.default.name
      source_ranges = [var.ssh_allowed_cidr]
      target_tags   = [local.gcp_name]

      allow {
        protocol = "tcp"
        ports    = ["300"]
      }
    }

    output "firewall_name" {
      value = google_compute_firewall.ssh.name
    }
  }
}
