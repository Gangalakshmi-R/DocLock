package com.doclock.backend.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "document_facts")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DocumentFact {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "document_id", nullable = false)
    private Document document;

    @Column(nullable = false)
    private String factType;

    @Column(nullable = false)
    private String keyName;

    @Column(columnDefinition = "TEXT", nullable = false)
    private String value;

    private Integer pageNumber;
}
