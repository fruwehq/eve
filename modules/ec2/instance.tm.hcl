generate_hcl "z_ec2_instance.tf" {
  content {
    data "aws_ami" "windows" {
      most_recent = true
      owners      = ["amazon"]
      filter {
        name   = "name"
        values = ["Windows_Server-2025-English-Full-Base-2026*"]
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

    data "aws_vpc" "default" {
      filter {
        name   = "tag:Environment"
        values = [global.project_name]
      }

      filter {
        name   = "tag:Project"
        values = [global.project_name]
      }
    }

    data "aws_security_group" "default" {
      name = global.aws.security_group.name
    }

    data "aws_subnets" "default" {
      filter {
        name   = "vpc-id"
        values = [data.aws_vpc.default.id]
      }

      filter {
        name   = "availability-zone"
        values = [global.availability_zone]
      }

      filter {
        name   = "default-for-az"
        values = ["true"]
      }
    }

    resource "aws_iam_role" "windows" {
      name = "ephemeral-cloud-gaming-windows"
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
    resource "aws_iam_role_policy_attachment" "windows_ssm" {
      role       = aws_iam_role.windows.name
      policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    }
    resource "aws_iam_instance_profile" "windows" {
      name = "ephemeral-cloud-gaming-windows"
      role = aws_iam_role.windows.name
    }

    resource "aws_instance" "windows" {
      ami                                  = data.aws_ami.windows.id
      instance_type                        = global.instance_type
      subnet_id                            = data.aws_subnets.default.ids[0]
      vpc_security_group_ids               = [data.aws_security_group.default.id]
      iam_instance_profile                 = aws_iam_instance_profile.windows.name
      instance_initiated_shutdown_behavior = "stop"

      root_block_device {
        volume_type           = "gp3"
        volume_size           = 200
        delete_on_termination = true
      }

      metadata_options {
        http_tokens = "required"
      }

      tm_dynamic "instance_market_options" {
        condition = tm_can(global.use_spot)

        content {
          market_type = "spot"
          spot_options {
            instance_interruption_behavior = "stop"
          }
        }
      }

      tags = tm_merge(global.aws.tags, {
        Name = "ephemeral-cloud-gaming-windows"
      })
    }

    output "instance_id" {
      value = aws_instance.windows.id
    }

    output "public_ip" {
      value = aws_instance.windows.public_ip
    }
  }
}
