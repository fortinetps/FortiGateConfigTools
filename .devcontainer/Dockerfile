# specify alpine3.14 just because I need OpenSSH_8.6p1 (not OpenSSH_9.0_p1-r1)
# which I can specify legacy KexAlgorithms in sshd_config
# because I have an older version of SecureCRT running on my PC
FROM python:3.7-alpine3.14
USER root
RUN apk update
RUN apk add --no-cache openssh screen git
RUN /usr/bin/ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N '' -t rsa
RUN echo 'root:secretpassword' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/g' /etc/ssh/sshd_config
RUN echo "#Legacy changes" >> /etc/ssh/sshd_config
RUN echo "KexAlgorithms diffie-hellman-group1-sha1" >> /etc/ssh/sshd_config
RUN echo "Ciphers aes128-cbc" >> /etc/ssh/sshd_config
EXPOSE 22