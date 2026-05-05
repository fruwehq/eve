generate_hcl "z_ec2_instance.tf" {
  content {
    # ── Profile-driven variables (overridden via TF_VAR_* from profile-tf-env) ──

    variable "profile_name" {
      type        = string
      default     = "dev-sandbox"
      description = "Profile name used for resource naming and tagging"
    }

    variable "os_family" {
      type        = string
      default     = "ubuntu"
      description = "OS family: ubuntu or windows"

      validation {
        condition     = contains(["ubuntu", "windows"], var.os_family)
        error_message = "os_family must be ubuntu or windows."
      }
    }

    variable "instance_type" {
      type        = string
      default     = "t3.large"
      description = "EC2 instance type"
    }

    variable "disk_gb" {
      type        = number
      default     = 80
      description = "Root volume size in GB"
    }

    variable "root_volume_type" {
      type        = string
      default     = "gp3"
      description = "Root volume type (e.g., gp3, gp2)"
    }

    variable "bundle_packages" {
      type        = string
      default     = "ssh"
      description = "Comma-separated list of bundle packages for conditional configuration"
    }

    variable "use_spot" {
      type        = bool
      default     = false
      description = "Use spot instance pricing"
    }

    variable "ssh_public_key_file" {
      type = string
    }

    variable "availability_zone" {
      type        = string
      description = "AWS availability zone (from profile location mapping via TF_VAR_availability_zone)"
    }

    # ── AMI Lookup (both always generated, selected by count) ─────────────

    data "aws_ami" "ubuntu" {
      count = var.os_family == "ubuntu" ? 1 : 0

      most_recent = true
      owners      = ["099720109477"] # Canonical

      filter {
        name   = "name"
        values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-resolute-26.04-amd64-server-*"]
      }

      filter {
        name   = "virtualization-type"
        values = ["hvm"]
      }

      filter {
        name   = "architecture"
        values = ["x86_64"]
      }

      filter {
        name   = "root-device-type"
        values = ["ebs"]
      }
    }

    data "aws_ami" "windows" {
      count = var.os_family == "windows" ? 1 : 0

      most_recent = true
      owners      = ["amazon"]

      filter {
        name   = "name"
        values = ["Windows_Server-2025-English-Full-Base-*"]
      }

      filter {
        name   = "virtualization-type"
        values = ["hvm"]
      }

      filter {
        name   = "architecture"
        values = ["x86_64"]
      }

      filter {
        name   = "root-device-type"
        values = ["ebs"]
      }
    }

    # ── VPC / Subnet / Security Group ─────────────────────────────────────

    data "aws_vpcs" "default" {
      filter {
        name   = "isDefault"
        values = ["true"]
      }
    }

    locals {
      sg_name = "profile-${replace(var.profile_name, "_", "-")}"
    }

    data "aws_security_group" "default" {
      name   = local.sg_name
      vpc_id = data.aws_vpcs.default.ids[0]
    }

    data "aws_subnets" "default" {
      filter {
        name   = "vpc-id"
        values = [data.aws_vpcs.default.ids[0]]
      }

      filter {
        name   = "availability-zone"
        values = [var.availability_zone]
      }

      filter {
        name   = "default-for-az"
        values = ["true"]
      }
    }

    # ── IAM Role & Instance Profile ───────────────────────────────────────

    resource "aws_iam_role" "main" {
      name = var.profile_name

      assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [{
          Action = "sts:AssumeRole"
          Effect = "Allow"
          Principal = {
            Service = "ec2.amazonaws.com"
          }
        }]
      })
    }

    resource "aws_iam_role_policy_attachment" "ssm" {
      role       = aws_iam_role.main.name
      policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    }

    resource "aws_iam_instance_profile" "main" {
      name = var.profile_name
      role = aws_iam_role.main.name
    }

    # ── Cloud-Init (Ubuntu only, via count) ───────────────────────────────

    data "cloudinit_config" "ubuntu" {
      count = var.os_family == "ubuntu" ? 1 : 0

      gzip          = false
      base64_encode = true

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

    # ── EC2 Instance ──────────────────────────────────────────────────────

    resource "aws_instance" "main" {
      ami                                  = var.os_family == "ubuntu" ? data.aws_ami.ubuntu[0].id : data.aws_ami.windows[0].id
      instance_type                        = var.instance_type
      subnet_id                            = data.aws_subnets.default.ids[0]
      vpc_security_group_ids               = [data.aws_security_group.default.id]
      iam_instance_profile                 = aws_iam_instance_profile.main.name
      instance_initiated_shutdown_behavior = "stop"
      user_data                            = var.os_family == "ubuntu" ? data.cloudinit_config.ubuntu[0].rendered : null

      root_block_device {
        volume_type           = var.root_volume_type
        volume_size           = var.disk_gb
        delete_on_termination = true
      }

      metadata_options {
        http_tokens = "required"
      }

      dynamic "instance_market_options" {
        for_each = var.use_spot ? [1] : []

        content {
          market_type = "spot"
          spot_options {
            instance_interruption_behavior = "stop"
          }
        }
      }

      tags = {
        Project   = global.aws.tags.Project
        ManagedBy = global.aws.tags.ManagedBy
        Name      = var.profile_name
      }
    }

    # ── Outputs ───────────────────────────────────────────────────────────

    output "instance_id" {
      value = aws_instance.main.id
    }

    output "public_ip" {
      value = aws_instance.main.public_ip
    }
  }
}
