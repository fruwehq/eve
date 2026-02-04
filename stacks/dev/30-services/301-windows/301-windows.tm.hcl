stack {
  name = "301 Windows"

  tags = [
    "dev",
    "services",
    "windows",
  ]

  after = [
    "/stacks/dev/20-shared",
  ]
}

globals {
  availability_zone = "ap-northeast-1c"
  # instance_type  = "g5.2xlarge"
  instance_type  = "g5.xlarge"
  use_spot       = true
}

import {
  source = "/modules/ec2/instance.tm.hcl"
}
