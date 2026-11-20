terraform {
  required_version = ">= 1.6.0"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "2.108.0"
    }
  }
}

# The token comes from DIGITALOCEAN_TOKEN. The zone is never delegated, so the
# records exist only in DigitalOcean's API and serve no real DNS traffic.
variable "zone" {
  type = string
}

variable "region" {
  type    = string
  default = "lon1"
}

variable "ssh_public_key" {
  type = string
}

# A documentation range (RFC 5737): nobody can reach port 22 from it.
variable "admin_cidr" {
  type    = string
  default = "203.0.113.0/24"
}

resource "digitalocean_tag" "web" {
  name = "dl-web"
}

resource "digitalocean_tag" "env" {
  name = "dl-env-lab"
}

resource "digitalocean_ssh_key" "lab" {
  name       = "dl-lab"
  public_key = var.ssh_public_key
}

resource "digitalocean_droplet" "web" {
  name       = "dl-web-1"
  region     = var.region
  size       = "s-1vcpu-512mb-10gb"
  image      = "ubuntu-24-04-x64"
  ssh_keys   = [digitalocean_ssh_key.lab.fingerprint]
  tags       = [digitalocean_tag.web.id, digitalocean_tag.env.id]
  backups    = false
  monitoring = false
}

# Applies to every droplet tagged dl-web, not to a list of droplet IDs.
resource "digitalocean_firewall" "web" {
  name = "dl-web"
  tags = [digitalocean_tag.web.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.admin_cidr]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_domain" "lab" {
  name = var.zone
}

resource "digitalocean_record" "app" {
  domain = digitalocean_domain.lab.id
  type   = "A"
  name   = "app"
  value  = digitalocean_droplet.web.ipv4_address
  ttl    = 1800
}

resource "digitalocean_record" "www" {
  domain = digitalocean_domain.lab.id
  type   = "CNAME"
  name   = "www"
  value  = "app.${var.zone}."
  ttl    = 1800
}

resource "digitalocean_record" "verify" {
  domain = digitalocean_domain.lab.id
  type   = "TXT"
  name   = "@"
  value  = "site-verification=drift-lab"
  ttl    = 3600
}

resource "digitalocean_project" "lab" {
  name        = "drift-lab"
  description = "Terraform drift lab. Safe to delete."
  purpose     = "Class project / Educational purposes"
  environment = "Development"
  resources   = [digitalocean_droplet.web.urn, digitalocean_domain.lab.urn]
}
