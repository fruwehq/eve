generate_hcl "z_ec2_instance.tf" {
  content {
    data "aws_ami" "windows_2022" {
      most_recent = true
      owners      = ["amazon"]
      filter {
        name   = "name"
        values = ["Windows_Server-2022-English-Full-Base-*"]
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
      ami                         = data.aws_ami.windows_2022.id
      instance_type               = try(global.instance_type, "g5.2xlarge")
      subnet_id                   = local.default_subnet_id
      vpc_security_group_ids      = [aws_security_group.windows.id]
      iam_instance_profile        = aws_iam_instance_profile.windows.name
      instance_initiated_shutdown_behavior = "stop"

      root_block_device {
        volume_type           = "gp3"
        volume_size           = 200
        delete_on_termination = true
      }

      metadata_options {
        http_tokens = "required"
      }

      dynamic "instance_market_options" {
        for_each = local.use_spot ? [1] : []
        content {
          market_type = "spot"
          spot_options {
            instance_interruption_behavior = local.spot_interruption_behavior
          }
        }
      }

      tags = merge(var.tags, {
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
