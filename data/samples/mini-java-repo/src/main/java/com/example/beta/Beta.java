package com.example.beta;

import com.example.alpha.Alpha;

public class Beta {
    private Alpha alpha;
    public void doBeta() { /* uses alpha elsewhere */ }
    public String owner() { return new Alpha().name(); }
}
