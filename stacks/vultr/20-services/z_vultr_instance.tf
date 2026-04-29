// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

variable "profile_name" {
  type = string
}
variable "os_family" {
  type = string
  validation {
    condition = contains([
      "ubuntu",
      "windows",
    ], var.os_family)
    error_message = "os_family must be ubuntu or windows."
  }
}
variable "plan" {
  type = string
}
variable "region" {
  type = string
}
variable "vultr_os_id" {
  description = "Vultr numeric OS ID (from `vultr-cli os list`, resolved via catalog)"
  type        = number
}
variable "ssh_public_key_file" {
  type = string
}
locals {
  is_windows = var.os_family == "windows"
  linux_user_data = yamlencode({
    hostname         = replace(var.profile_name, "_", "-")
    manage_etc_hosts = true
    users = [
      {
        name        = "ubuntu"
        sudo        = "ALL=(ALL) NOPASSWD:ALL"
        shell       = "/bin/bash"
        lock_passwd = false
        ssh_authorized_keys = [
          trimspace(file(pathexpand(var.ssh_public_key_file))),
        ]
      },
    ]
    package_update  = true
    package_upgrade = false
    packages = [
      "curl",
      "git",
      "jq",
      "unzip",
    ]
  })
}
resource "vultr_startup_script" "windows_ssh" {
  count = local.is_windows ? 1 : 0
  name  = "${var.profile_name}-windows-ssh"
  script = base64encode(templatefile("/Users/chris/src/personal/ephemeral-cloud-gaming-dev-tools/modules/vultr/templates/windows-startup.cmd.tftpl", {
    encoded_command = textencodebase64(templatefile("/Users/chris/src/personal/ephemeral-cloud-gaming-dev-tools/windows/ssh.ps1.tftpl", {
      public_key = trimspace(file(pathexpand(var.ssh_public_key_file)))
    }), "UTF-16LE")
  }))
  type = "boot"
}
resource "vultr_instance" "default" {
  backups   = "disabled"
  hostname  = replace(var.profile_name, "_", "-")
  label     = var.profile_name
  os_id     = var.vultr_os_id
  plan      = var.plan
  region    = var.region
  script_id = local.is_windows ? vultr_startup_script.windows_ssh[0].id : null
  user_data = local.is_windows ? null : base64encode("#cloud-config\n${local.linux_user_data}")
}
output "instance_id" {
  value = vultr_instance.default.id
}
output "vultr_instance_default_password" {
  description = "Default password (Windows only — empty for Linux cloud-init profiles)"
  sensitive   = true
  value       = vultr_instance.default.default_password
}
output "vultr_instance_main_ip" {
  value = vultr_instance.default.main_ip
}
output "public_ip" {
  value = vultr_instance.default.main_ip
}
