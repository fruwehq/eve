generate_hcl "z_ec2_security_group.tf" {
  content {
    # ── Profile-driven variables (overridden via TF_VAR_* from profile-tf-env) ──

    variable "profile_name" {
      type        = string
      default     = "dev-sandbox"
      description = "Profile name used for security group naming"
    }

    variable "os_family" {
      type        = string
      default     = "ubuntu"
      description = "OS family: ubuntu or windows"
    }

    variable "bundle_packages" {
      type        = string
      default     = "ssh"
      description = "Comma-separated list of bundle packages for rule selection"
    }

    data "aws_vpcs" "default" {
      filter {
        name   = "isDefault"
        values = ["true"]
      }
    }

    locals {
      sg_name     = "profile-${replace(var.profile_name, "_", "-")}"
      package_set = toset(split(",", var.bundle_packages))
    }

    resource "aws_security_group" "default" {
      name        = local.sg_name
      description = "Security group for profile: ${var.profile_name}"
      vpc_id      = data.aws_vpcs.default.ids[0]

      # ── Base (always included) ────────────────────────────────────────

      ingress {
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = local.allowed_cidrs
        description = "SSH"
      }

      # ── Sunshine / Moonlight ──────────────────────────────────────────

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 47984
          to_port     = 47984
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 47989
          to_port     = 47989
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 47990
          to_port     = 47990
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "Sunshine Web UI"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 47998
          to_port     = 47998
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 47999
          to_port     = 47999
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 48000
          to_port     = 48000
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 48002
          to_port     = 48002
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 48010
          to_port     = 48010
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "sunshine") ? [1] : []

        content {
          from_port   = 48010
          to_port     = 48010
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Moonlight UDP"
        }
      }

      # ── Steam ─────────────────────────────────────────────────────────

      dynamic "ingress" {
        for_each = contains(local.package_set, "steam") ? [1] : []

        content {
          from_port   = 27031
          to_port     = 27031
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Steam UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "steam") ? [1] : []

        content {
          from_port   = 27036
          to_port     = 27036
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "Steam TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "steam") ? [1] : []

        content {
          from_port   = 27037
          to_port     = 27037
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "Steam UDP"
        }
      }

      # ── RustDesk ──────────────────────────────────────────────────────

      dynamic "ingress" {
        for_each = contains(local.package_set, "rustdesk") ? [1] : []

        content {
          from_port   = 21116
          to_port     = 21116
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "RustDesk TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "rustdesk") ? [1] : []

        content {
          from_port   = 21116
          to_port     = 21116
          protocol    = "udp"
          cidr_blocks = local.allowed_cidrs
          description = "RustDesk UDP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "rustdesk") ? [1] : []

        content {
          from_port   = 21117
          to_port     = 21117
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "RustDesk TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "rustdesk") ? [1] : []

        content {
          from_port   = 21118
          to_port     = 21118
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "RustDesk TCP"
        }
      }

      dynamic "ingress" {
        for_each = contains(local.package_set, "rustdesk") ? [1] : []

        content {
          from_port   = 21119
          to_port     = 21119
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "RustDesk TCP"
        }
      }

      # ── ThinLinc ─────────────────────────────────────────────────────

      dynamic "ingress" {
        for_each = contains(local.package_set, "thinlinc") ? [1] : []

        content {
          from_port   = 300
          to_port     = 300
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "ThinLinc Web Access"
        }
      }

      # ── Windows-specific ──────────────────────────────────────────────

      dynamic "ingress" {
        for_each = var.os_family == "windows" ? [1] : []

        content {
          from_port   = 3389
          to_port     = 3389
          protocol    = "tcp"
          cidr_blocks = local.allowed_cidrs
          description = "RDP"
        }
      }

      # ── Egress ────────────────────────────────────────────────────────

      egress {
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = ["0.0.0.0/0"]
        ipv6_cidr_blocks = ["::/0"]
        description      = "Allow all egress"
      }
    }
  }
}
