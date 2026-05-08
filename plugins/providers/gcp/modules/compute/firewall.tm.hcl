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

    data "google_compute_network" "default" {
      name = "default"
    }

    locals {
      gcp_name = substr(replace(lower(var.profile_name), "_", "-"), 0, 52)
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

    output "firewall_name" {
      value = google_compute_firewall.ssh.name
    }
  }
}
