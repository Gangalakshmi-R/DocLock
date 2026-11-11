package com.doclock.backend.controller;

import com.doclock.backend.dto.LoginRequest;
import com.doclock.backend.security.JwtService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.security.Principal;
import java.util.Map;
import java.util.Objects;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final JwtService jwtService;

    @Value("${doclock.security.username}")
    private String configuredUsername;

    @Value("${doclock.security.password}")
    private String configuredPassword;

    public AuthController(JwtService jwtService) { this.jwtService = jwtService; }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody LoginRequest request) {
        boolean valid = request != null
                && Objects.equals(configuredUsername, request.username())
                && Objects.equals(configuredPassword, request.password());

        if (!valid) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("message", "Invalid username or password."));
        }

        return ResponseEntity.ok(Map.of(
                "token", jwtService.generateToken(configuredUsername),
                "username", configuredUsername
        ));
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
