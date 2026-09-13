ARG NGINX_IMAGE
FROM ${NGINX_IMAGE}
COPY nginx-entrypoint.sh /usr/local/bin/cloud-nginx-entrypoint
RUN chmod 0755 /usr/local/bin/cloud-nginx-entrypoint
ENTRYPOINT ["/usr/local/bin/cloud-nginx-entrypoint"]
