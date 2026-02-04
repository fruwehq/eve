generate_hcl "z_ec2_security_group.tf" {
  content {
    resource "aws_security_group" "windows" {
      name        = "ephemeral-cloud-gaming-windows"
      description = "Security group for ephemeral cloud gaming Windows"
      vpc_id      = aws_default_vpc.default.id

      ingress {
        from_port   = 80
        to_port     = 80
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "HTTP"
      }
      ingress {
        from_port   = 443
        to_port     = 443
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "HTTPS"
      }
      ingress {
        from_port   = 3389
        to_port     = 3389
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "RDP"
      }
      ingress {
        from_port   = 8443
        to_port     = 8443
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "NICE DCV"
      }
      ingress {
        from_port   = 8443
        to_port     = 8443
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "NICE DCV"
      }
      ingress {
        from_port   = 48010
        to_port     = 48010
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 48010
        to_port     = 48010
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 47984
        to_port     = 47984
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 47989
        to_port     = 47989
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 47998
        to_port     = 47998
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 47999
        to_port     = 47999
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 48000
        to_port     = 48000
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 48002
        to_port     = 48002
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Moonlight"
      }
      ingress {
        from_port   = 27036
        to_port     = 27036
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "Steam"
      }
      ingress {
        from_port   = 27031
        to_port     = 27031
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Steam"
      }
      ingress {
        from_port   = 27037
        to_port     = 27037
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "Steam"
      }
      ingress {
        from_port   = 8000
        to_port     = 8000
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "RustDesk Server"
      }
      ingress {
        from_port   = 21114
        to_port     = 21114
        protocol    = "tcp"
        cidr_blocks = global.allowed_cidrs
        description = "RustDesk Server"
      }
      ingress {
        from_port   = 21116
        to_port     = 21116
        protocol    = "udp"
        cidr_blocks = global.allowed_cidrs
        description = "RustDesk Server"
      }
      egress {
        from_port   = 0
        to_port     = 0
        protocol    = "-1"
        cidr_blocks = ["0.0.0.0/0"]
        ipv6_cidr_blocks = ["::/0"]
        description = "Allow all egress"
      }
    }
  }
}
