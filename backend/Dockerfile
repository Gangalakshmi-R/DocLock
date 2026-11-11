# Build the Spring Boot application with Java 21.
FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -B -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests clean package

# Run with a smaller Java 21 runtime image.
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/doclock/storage && useradd --system --uid 10001 doclock
COPY --from=build /app/target/*.jar app.jar
RUN chown -R doclock:doclock /app /var/doclock
USER doclock
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
