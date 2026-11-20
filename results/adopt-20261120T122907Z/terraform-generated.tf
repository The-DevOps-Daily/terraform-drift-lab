# __generated__ by Terraform
# Please review these resources and move them into your main configuration files.

# __generated__ by Terraform from "tf-drift-lab.devops-daily.com,1839110511"
resource "digitalocean_record" "adopted_3" {
  domain   = "tf-drift-lab.devops-daily.com"
  flags    = 0
  name     = "debug"
  port     = 0
  priority = 0
  tag      = null
  ttl      = 60
  type     = "A"
  value    = "198.51.100.8"
  weight   = 0
}

# __generated__ by Terraform from "dl-owner-oncall"
resource "digitalocean_tag" "adopted_2" {
  name = "dl-owner-oncall"
}

# __generated__ by Terraform from "6b7cf463-0391-436a-b901-15f990863561"
resource "digitalocean_firewall" "adopted_1" {
  droplet_ids = [621604794]
  name        = "dl-hotfix-8080"
  tags        = []
  inbound_rule {
    action                    = "allow"
    port_range                = "8080"
    protocol                  = "tcp"
    source_addresses          = ["0.0.0.0/0", "::/0"]
    source_droplet_ids        = []
    source_kubernetes_ids     = []
    source_load_balancer_uids = []
    source_tags               = []
  }
}

# __generated__ by Terraform from "621617516"
resource "digitalocean_droplet" "adopted_0" {
  backups            = false
  droplet_agent      = null
  gpu_partition_mode = null
  graceful_shutdown  = null
  image              = "ubuntu-24-04-x64"
  ipv6               = false
  monitoring         = false
  name               = "dl-web-debug"
  public_networking  = true
  region             = "lon1"
  resize_disk        = true
  size               = "s-1vcpu-512mb-10gb"
  ssh_keys           = null
  tags               = ["dl-owner-oncall", "dl-web"]
  user_data          = null
  volume_ids         = []
  vpc_uuid           = "<default-vpc-uuid, redacted>"
}
