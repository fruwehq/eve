# TrueNAS VM module (real provider resource)

generate_hcl "z_truenas_vm.tf" {
  content {
    variable "profile_name" {
      type = string
    }

    variable "os_id" {
      type = string
    }

    variable "location_name" {
      type = string
    }

    variable "vm_memory_mb" {
      type    = number
      default = 8192
    }

    variable "vm_cpu_cores" {
      type    = number
      default = 4
    }

    variable "vm_vcpus" {
      type    = number
      default = 1
    }

    variable "vm_autostart" {
      type    = bool
      default = true
    }

    variable "vm_state" {
      type    = string
      default = "RUNNING"
    }

    variable "vm_nic_attach" {
      type    = string
      default = "br0"
    }

    variable "vm_disk_gb" {
      type    = number
      default = 30
    }

    variable "vm_pool" {
      type    = string
      default = "main"
    }

    variable "vm_iso_dir" {
      type    = string
      default = "/mnt/main/iso"
    }

    variable "ssh_public_key_file" {
      type = string
    }

    variable "cloud_image_url" {
      type    = string
      default = ""
    }

    locals {
      vm_name  = join("", regexall("[a-zA-Z0-9]+", var.profile_name))
      iso_path = "${var.vm_iso_dir}/${local.vm_name}-cidata.iso"
    }

    resource "truenas_zvol" "this" {
      pool    = var.vm_pool
      path    = "vms/${local.vm_name}"
      volsize = "${var.vm_disk_gb}G"
      sparse  = true
    }

    resource "null_resource" "write_cloud_image" {
      count = var.cloud_image_url != "" ? 1 : 0

      triggers = {
        zvol_id        = truenas_zvol.this.id
        cloud_image_url = var.cloud_image_url
        truenas_host   = var.truenas_host
        vm_disk_gb     = var.vm_disk_gb
      }

      provisioner "local-exec" {
        command = "\"$(git rev-parse --show-toplevel)/scripts/truenas-image-write\" '${var.truenas_host}' '${self.triggers.zvol_id}' '${var.cloud_image_url}' '${var.vm_disk_gb}'"
      }
    }

    resource "null_resource" "cloudinit_iso" {
      # var.truenas_host is declared in stacks/truenas/20-services/providers.tm.hcl
      # (both generate_hcl blocks land in the same stack). Keep that in mind if this
      # module is ever lifted out to a standalone Terraform module.
      triggers = {
        vm_name        = local.vm_name
        truenas_host   = var.truenas_host
        iso_path       = local.iso_path
        ssh_public_key = trimspace(file(var.ssh_public_key_file))
      }

      provisioner "local-exec" {
        command = "\"$(git rev-parse --show-toplevel)/scripts/truenas-cloudinit-upload\" '${local.vm_name}' '${var.ssh_public_key_file}' '${var.truenas_host}' '${local.iso_path}'"
      }

      provisioner "local-exec" {
        when    = destroy
        command = "\"$(git rev-parse --show-toplevel)/scripts/truenas-cloudinit-delete\" '${self.triggers.truenas_host}' '${self.triggers.iso_path}'"
      }
    }

    resource "truenas_vm" "this" {
      depends_on  = [truenas_zvol.this, null_resource.cloudinit_iso, null_resource.write_cloud_image]
      autostart   = var.vm_autostart
      cores       = var.vm_cpu_cores
      description = "Profile=${var.profile_name}; OS=${var.os_id}; Location=${var.location_name}"
      memory      = var.vm_memory_mb
      name        = local.vm_name
      state       = var.vm_state
      vcpus       = var.vm_vcpus

      nic {
        nic_attach = var.vm_nic_attach
        type       = "VIRTIO"
      }

      disk {
        path = "/dev/zvol/${truenas_zvol.this.id}"
        type = "VIRTIO"
      }

      cdrom {
        path = local.iso_path
      }
    }

    output "truenas_vm_id" {
      value = truenas_vm.this.id
    }

    output "truenas_vm_name" {
      value = truenas_vm.this.name
    }
  }
}
