# Backup
docker run --rm \
  -v mainten_uploads:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/uploads-$(date +%Y%m%d).tgz -C /data .

# Restore
docker run --rm \
  -v mainten_uploads:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/uploads-YYYYMMDD.tgz -C /data
