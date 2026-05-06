# TrueNAS VM module (zvol-based disks with automated image writing)

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

    variable "vm_cpu_mode" {
      type    = string
      default = "CUSTOM"
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

    variable "vm_base_dir" {
      type    = string
      default = ""
    }

    variable "vm_pool" {
      type    = string
      default = "main"
    }

    variable "vm_zvol_prefix" {
      type    = string
      default = "vms"
    }

    variable "ssh_public_key_file" {
      type = string
    }

    variable "cloud_image_url" {
      type    = string
      default = ""
    }

    locals {
      vm_name     = join("", regexall("[a-zA-Z0-9]+", var.profile_name))
      base_dir    = var.vm_base_dir
      iso_path    = "${local.base_dir}/iso/${local.vm_name}-${var.os_id}-cidata.iso"
      images_dir  = "${local.base_dir}/images"
      zvol_path   = "${var.vm_zvol_prefix}/${local.vm_name}"
      zvol_device = "/dev/zvol/${var.vm_pool}/${local.zvol_path}"
    }

    resource "null_resource" "verify_parent_dataset" {
      triggers = {
        base_dir = local.base_dir
      }

      provisioner "local-exec" {
        command = "\"$(git rev-parse --show-toplevel)/scripts/truenas-dataset-verify\" '${local.base_dir}'"
      }
    }

    resource "truenas_zvol" "this" {
      depends_on = [null_resource.verify_parent_dataset]
      pool       = var.vm_pool
      path       = local.zvol_path
      sparse     = true
      volsize    = "${var.vm_disk_gb * 1024}M"
    }

    resource "null_resource" "write_cloud_image" {
      count = var.cloud_image_url != "" ? 1 : 0

      depends_on = [truenas_zvol.this]

      triggers = {
        zvol_id         = truenas_zvol.this.id
        cloud_image_url = var.cloud_image_url
        disk_gb         = var.vm_disk_gb
      }

      provisioner "local-exec" {
        command = join(" ", [
          "\"$(git rev-parse --show-toplevel)/scripts/truenas-vm-disk-prepare\"",
          "'${var.truenas_host}'",
          "'${local.images_dir}'",
          "'${local.zvol_device}'",
          "'${local.vm_name}'",
          "'${var.cloud_image_url}'",
          "'${var.vm_disk_gb}'",
        ])
      }
    }

    resource "null_resource" "cloudinit_iso" {
      triggers = {
        vm_name        = local.vm_name
        os_id          = var.os_id
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
      depends_on = [
        null_resource.write_cloud_image,
        null_resource.cloudinit_iso,
      ]
      autostart   = var.vm_autostart
      cores       = var.vm_cpu_cores
      cpu_mode    = var.vm_cpu_mode
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
        path = local.zvol_device
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

    output "truenas_vm_mac" {
      value = try(truenas_vm.this.nic[0].mac, "")
    }
  }
}
