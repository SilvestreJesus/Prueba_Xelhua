FROM xel_base_yaml_creator:v2.0

ADD ./app .

WORKDIR /home/app/puzzlemesh/
RUN cmake -S . -B build
WORKDIR /home/app/puzzlemesh/build/
RUN make
RUN cp puzzlemesh /home/app/puzzlemesh
WORKDIR /home/app/