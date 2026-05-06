generate_hcl "z_gcp_instance.tf" {
  content {
    variable "profile_name" {
      type        = string
      default     = "dev-sandbox"
      description = "Instance/profile name used for resource naming"
    }

    variable "os_family" {
      type        = string
      default     = "ubuntu"
      description = "OS family"

      validation {
        condition     = contains(["ubuntu"], var.os_family)
        error_message = "gcp currently supports ubuntu instances."
      }
    }

    variable "machine_type" {
      type        = string
      default     = "e2-small"
      description = "GCP machine type"
    }

    variable "disk_gb" {
      type        = number
      default     = 20
      description = "Boot disk size in GB"
    }

    variable "disk_type" {
      type        = string
      default     = "pd-balanced"
      description = "Boot disk type"
    }

    variable "image_project" {
      type        = string
      description = "GCP image project"
    }

    variable "image_family" {
      type        = string
      description = "GCP image family"
    }

    variable "bundle_packages" {
      type        = string
      default     = "ssh"
      description = "Comma-separated package list"
    }

    variable "ssh_public_key_file" {
      type = string
    }

    data "google_compute_image" "ubuntu" {
      family  = var.image_family
      project = var.image_project
    }

    data "cloudinit_config" "ubuntu" {
      gzip          = false
      base64_encode = false

      part {
        filename     = "cloud-config.yaml"
        content_type = "text/cloud-config"

        content = yamlencode({
          hostname         = replace(var.profile_name, "_", "-")
          manage_etc_hosts = true

          users = [{
            name                = "ubuntu"
            sudo                = "ALL=(ALL) NOPASSWD:ALL"
            shell               = "/bin/bash"
            lock_passwd         = false
            ssh_authorized_keys = [trimspace(file(pathexpand(var.ssh_public_key_file)))]
          }]

          package_update  = true
          package_upgrade = true

          packages = [
            "curl",
            "git",
            "jq",
          ]
        })
      }
    }

    locals {
      gcp_name       = substr(replace(lower(var.profile_name), "_", "-"), 0, 52)
      ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_file)))
    }

    resource "google_compute_instance" "main" {
      name         = local.gcp_name
      machine_type = var.machine_type
      tags         = [local.gcp_name]
      labels       = global.gcp.labels

      boot_disk {
        initialize_params {
          image = data.google_compute_image.ubuntu.self_link
          size  = var.disk_gb
          type  = var.disk_type
        }
      }

      network_interface {
        network = "default"

        access_config {
        }
      }

      metadata = {
        ssh-keys  = "ubuntu:${local.ssh_public_key}"
        user-data = data.cloudinit_config.ubuntu.rendered
      }

      scheduling {
        automatic_restart   = false
        on_host_maintenance = "MIGRATE"
      }
    }

    output "instance_id" {
      value = google_compute_instance.main.id
    }

    output "instance_name" {
      value = google_compute_instance.main.name
    }

    output "public_ip" {
      value = google_compute_instance.main.network_interface[0].access_config[0].nat_ip
    }
  }
}
