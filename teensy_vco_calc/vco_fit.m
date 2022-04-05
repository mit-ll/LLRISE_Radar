clear all; close all;
%% Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
%%
if (1)
    title_str = 'VCO voltage fit for a linear ramp';
    fname = 'vco_linear_coefs.h';
    v_tune = linspace(0.0,7.0,29).';
    freq = linspace(2257.4,2640.0,29).';
    tune_sens = ones(size(v_tune))*(freq(2)-freq(1))/(v_tune(2)-v_tune(1));
    vco_min_usable_freq = 2258.0;
    vco_max_usable_freq = 2518.0;
else
    title_str = 'VCO voltage fit for ROS-2536C-119+';
    fname = 'ROS_2536C_119.h';
    load('ROS-2536C-119+_Performance.mat');
    v_tune = ROS2536C119Performance(:,1);
    tune_sens = ROS2536C119Performance(:,2);
    freq = ROS2536C119Performance(:,4);
    vco_min_usable_freq = 2258.0;
    vco_max_usable_freq = 2588.0;
end

%%
pm=makima(freq,v_tune);

vco_freq_break=pm.breaks;
vco_voltage_c3=pm.coefs(:,1);
vco_voltage_c2=pm.coefs(:,2);
vco_voltage_c1=pm.coefs(:,3);
vco_voltage_c0=pm.coefs(:,4);
vco_poly_count = length(vco_voltage_c0);

%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Write a C file with VCO fit in it
fprintf('Creating: %s (%s)\n',title_str,fname);
fh=fopen(fname,'w');

fprintf(fh,'/*\n');
fprintf(fh,' * Auto-Generated VCO fit: %s\n',datestr(now(),'YYYY-mm-DD hh:MM:ss'));
fprintf(fh,' *                  Title: %s\n',title_str);
fprintf(fh,' *                   File: %s\n',fname);
fprintf(fh,' */\n');
fprintf(fh,'static const double vco_min_usable_freq = %7.1f; // MHz \n',vco_min_usable_freq);
fprintf(fh,'static const double vco_max_usable_freq = %7.1f; // MHz \n',vco_max_usable_freq);
fprintf(fh,'static const uint32_t vco_poly_count = %u;\n', vco_poly_count);
write_static_array(fh,'%7.1f','double','vco_freq_break',vco_freq_break);
write_static_array(fh,'%25.18e','double','vco_voltage_c3',vco_voltage_c3);
write_static_array(fh,'%25.18e','double','vco_voltage_c2',vco_voltage_c2);
write_static_array(fh,'%25.18e','double','vco_voltage_c1',vco_voltage_c1);
write_static_array(fh,'%25.18e','double','vco_voltage_c0',vco_voltage_c0);

fclose(fh);

%%
% C like test code in prep for writing it in C
%fstart=2257.4;
%fstop=2640.0;
fstart=2260.0;
fstop=2560.0;
fstop=2583.5;

fcount=3600;
fstep=(fstop-fstart)/(fcount-1);

val=zeros(fcount,1);
fi = 1;
ff = fstart;
for idx = 1:vco_poly_count
    while (ff >= vco_freq_break(idx)) && (ff <= vco_freq_break(idx+1))
        f0 = vco_freq_break(idx);
        x=ff-f0;
        val(fi)=((vco_voltage_c3(idx)*x + ...
            vco_voltage_c2(idx))*x + ...
            vco_voltage_c1(idx))*x + ...
            vco_voltage_c0(idx);
        ff = ff + fstep;
        fi = fi + 1;
        if fi>fcount, break; end;
    end
    if fi>fcount, break; end;
end
if fi < fcount
    error('bad range');
end

figure(4);
clf;
hold on;
plot(freq,v_tune,'bo')
plot(fstart+fstep*(0:(fcount-1)),val,'r+');
hold off;
grid on;

